"""CSV lead import. Every row goes through crud.create_lead (one path for all sources)."""

import csv
import hashlib
import io
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.leads import crud
from app.modules.leads.schemas import LeadCreate
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
MAX_ERRORS = 100
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
TRUE_VALUES = {"true", "yes", "y", "1"}
FALSE_VALUES = {"false", "no", "n", "0", ""}


def neutralize(value: str) -> str:
    """Stop spreadsheet formula injection."""
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

    if len(headers) != len(set(headers)):
        raise AuthError(422, "validation_error", "CSV contains duplicate column names")

    if "name" not in headers or not ({"email", "phone"} & set(headers)):
        raise AuthError(
            422,
            "validation_error",
            "CSV needs a 'name' column and an 'email' or 'phone' column",
        )

    reader.fieldnames = headers
    rows: list[tuple[int, dict[str, str]]] = []

    for number, row in enumerate(reader, start=2):
        if number - 1 > MAX_ROWS:
            raise AuthError(422, "validation_error", "Too many rows (maximum 10,000)")

        clean = {
            k: (v or "").strip()
            for k, v in row.items()
            if k and isinstance(v, str | None)
        }

        if any(clean.values()):
            rows.append((number, clean))

    return rows


def _resolve_assignee(
    session: Session,
    ctx: TenantContext,
    email: str,
) -> tuple[object, object]:
    """Resolve an assignee only from an active membership in this tenant."""
    normalized_email = email.strip().lower()

    membership = session.scalar(
        select(TenantMembership)
        .join(User, User.id == TenantMembership.user_id)
        .where(
            User.email == normalized_email,
            User.is_active.is_(True),
            TenantMembership.tenant_id == ctx.tenant_id,
            TenantMembership.is_active.is_(True),
        )
    )

    if membership is None:
        raise AuthError(
            422,
            "invalid_assignee",
            "Assigned user must be an active member of this company",
        )

    if membership.team_id is None:
        raise AuthError(
            422,
            "invalid_assignee",
            "Assigned user must belong to an active team",
        )

    return membership.user_id, membership.team_id


def _to_lead(clean: dict[str, str]) -> LeadCreate:
    requirement = neutralize(clean["requirement"]) if clean.get("requirement") else None
    existing_notes = neutralize(clean["notes"]) if clean.get("notes") else None

    if requirement and existing_notes:
        notes = f"Requirement: {requirement}\n{existing_notes}"
    elif requirement:
        notes = f"Requirement: {requirement}"
    else:
        notes = existing_notes

    consent_value = clean.get("consent", "").lower()

    if consent_value not in TRUE_VALUES | FALSE_VALUES:
        raise AuthError(
            422,
            "invalid_consent",
            "Consent must be yes/no, true/false, y/n, or 1/0",
        )

    return LeadCreate(
        name=neutralize(clean.get("name", "")),
        email=clean.get("email") or None,
        phone=clean.get("phone") or None,
        company_name=neutralize(clean["company_name"]) if clean.get("company_name") else None,
        source="csv",
        source_campaign=(
            neutralize(clean["source_campaign"]) if clean.get("source_campaign") else None
        ),
        external_id=(
            neutralize(clean["external_id"]) if clean.get("external_id") else None
        ),
        consent=consent_value in TRUE_VALUES,
        notes=notes,
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
    seen_external_ids: set[str] = set()

    def report(row: int, code: str, message: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append({"row": row, "code": code, "message": message})

    for number, clean in rows:
        try:
            body = _to_lead(clean)

            email = str(body.email).lower() if body.email else None
            phone = body.phone
            external_id = body.external_id

            if (
                (email and email in seen_emails)
                or (phone and phone in seen_phones)
                or (external_id and external_id in seen_external_ids)
            ):
                duplicates += 1
                report(number, "duplicate_in_file", "Same email, phone, or external ID as an earlier row")
                continue

            assigned_user_id = None
            team_id = None

            assigned_to = clean.get("assigned_to", "").strip()
            if assigned_to:
                assigned_user_id, team_id = _resolve_assignee(session, ctx, assigned_to)
                assigned_user_id, team_id = crud._validate_assignment(
                    session, ctx, assigned_user_id, team_id
                )

            if dry_run:
                crud._check_duplicate(
                    session,
                    ctx,
                    email=email,
                    phone=phone,
                    source=body.source,
                    external_id=body.external_id,
                )
            else:
                body = body.model_copy(
                    update={
                        "assigned_user_id": assigned_user_id,
                        "team_id": team_id,
                    }
                )
                row_key = hashlib.sha256(
                    f"{idempotency_key}:{number}".encode()
                ).hexdigest()
                crud.create_lead(session, ctx, body, row_key)

            created += 1
            if email:
                seen_emails.add(email)
            if phone:
                seen_phones.add(phone)
            if external_id:
                seen_external_ids.add(external_id)

        except ValidationError as exc:
            failed += 1
            field = str(exc.errors()[0]["loc"][0]) if exc.errors() else "row"
            report(number, "invalid_row", f"Invalid value in '{field}'")

        except AuthError as exc:
            if exc.code == "duplicate_lead":
                duplicates += 1
                report(number, "duplicate_lead", "A lead with this email, phone, or external ID already exists")
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
        "created_count": created,
        "duplicate_count": duplicates,
        "error_count": failed,
        "errors": errors,
    }
