"""CSV lead import. Every row goes through crud.create_lead (one path for all sources)."""

import csv
import hashlib
import io
import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.leads import crud
from app.modules.leads.schemas import LeadCreate

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
MAX_ERRORS = 100
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
TRUE_VALUES = {"true", "yes", "y", "1"}


def neutralize(value: str) -> str:
    """Stop spreadsheet formula injection: a leading = + - @ becomes harmless text."""
    value = value.strip()
    return "'" + value if value and value[0] in FORMULA_STARTS else value


def parse_csv(raw: bytes) -> list[tuple[int, dict[str, str]]]:
    if len(raw) > MAX_BYTES:
        raise AuthError(413, "payload_too_large", "CSV is larger than 10 MB")
    try:
        text_data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AuthError(422, "validation_error", "CSV must be UTF-8 text") from exc

    reader = csv.DictReader(io.StringIO(text_data))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    if "name" not in headers or not ({"email", "phone"} & set(headers)):
        raise AuthError(
            422, "validation_error", "CSV needs a 'name' column and an 'email' or 'phone' column"
        )
    reader.fieldnames = headers

    rows: list[tuple[int, dict[str, str]]] = []
    for number, row in enumerate(reader, start=2):  # row 1 is the header
        if number - 1 > MAX_ROWS:
            raise AuthError(422, "validation_error", "Too many rows (maximum 10,000)")
        clean = {k: (v or "").strip() for k, v in row.items() if k and isinstance(v, str | None)}
        if any(clean.values()):
            rows.append((number, clean))
    return rows


def _to_lead(clean: dict[str, str]) -> LeadCreate:
    return LeadCreate(
        name=neutralize(clean.get("name", "")),
        email=clean.get("email") or None,
        phone=clean.get("phone") or None,
        company_name=neutralize(clean["company_name"]) if clean.get("company_name") else None,
        consent=clean.get("consent", "").lower() in TRUE_VALUES,
        notes=neutralize(clean["notes"]) if clean.get("notes") else None,
        source="csv",
    )


def import_csv(
    session: Session,
    ctx: TenantContext,
    raw: bytes,
    dry_run: bool,
    idempotency_key: str,
) -> dict:
    rows = parse_csv(raw)
    created = duplicates = failed = 0
    errors: list[dict] = []
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()

    def report(row: int, code: str, message: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append({"row": row, "code": code, "message": message})

    for number, clean in rows:
        try:
            body = _to_lead(clean)
        except ValidationError as exc:
            failed += 1
            field = str(exc.errors()[0]["loc"][0]) if exc.errors() else "row"
            report(number, "invalid_row", f"Invalid value in '{field}'")
            continue

        email = str(body.email).lower() if body.email else None
        phone = body.phone
        if (email and email in seen_emails) or (phone and phone in seen_phones):
            duplicates += 1
            report(number, "duplicate_in_file", "Same email or phone as an earlier row")
            continue

        try:
            if dry_run:
                crud._check_duplicate(session, ctx, email=email, phone=phone)
            else:
                # One stable key per row: re-sending the same import never creates twice.
                row_key = hashlib.sha256(f"{idempotency_key}:{number}".encode()).hexdigest()
                crud.create_lead(session, ctx, body, row_key)
            created += 1
            if email:
                seen_emails.add(email)
            if phone:
                seen_phones.add(phone)
        except AuthError as exc:
            if exc.code == "duplicate_lead":
                duplicates += 1
                report(number, "duplicate_lead", "A lead with this email or phone already exists")
            else:
                failed += 1
                report(number, exc.code, exc.message)
        except Exception:
            logger.exception("CSV import failed on row %s", number)
            session.rollback()
            failed += 1
            report(number, "internal_error", "This row could not be imported")

    if dry_run:
        session.rollback()
    return {
        "status": "completed",
        "dry_run": dry_run,
        "total_rows": len(rows),
        "created_count": created,  # in a dry run: "would be created"
        "duplicate_count": duplicates,
        "error_count": failed,
        "errors": errors,
    }
