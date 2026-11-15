"""Single entry point for creating leads. Every channel calls capture_lead().

The caller owns the transaction: it must already have verified the tenant and called
set_tenant_context(), and it commits after this returns. This function only flushes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.leads.capture_normalize import (
    InvalidContact,
    clean_name,
    normalize_email,
    normalize_phone,
)
from app.modules.leads.models import Interaction, Lead

VALID_SOURCES = {
    "website_form",
    "tracking",
    "whatsapp",
    "facebook_lead_ads",
    "messenger",
    "manual",
    "csv",
}
VALID_CONSENT_SOURCES = {"web_form", "whatsapp", "manual", "import", "api"}
VALID_INTERACTIONS = {
    "form_submit",
    "page_view",
    "pricing_view",
    "demo_request",
    "call",
    "note",
    "import",
}
DEFAULT_CONSENT_SOURCE = {
    "website_form": "web_form",
    "whatsapp": "whatsapp",
    "csv": "import",
    "manual": "manual",
}
DEFAULT_INTERACTION = {"website_form": "form_submit", "tracking": "page_view", "csv": "import"}


class CaptureError(ValueError):
    """The input cannot be captured (maps to HTTP 422 in routers)."""


@dataclass
class CaptureInput:
    name: str
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    source: str = "manual"
    source_campaign: str | None = None
    external_id: str | None = None
    consent: bool = False
    consent_source: str | None = None
    notes: str | None = None
    interaction_type: str | None = None
    interaction_metadata: dict = field(default_factory=dict)
    # Already authorized by the caller (manager/admin choice or round-robin result).
    assigned_user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


@dataclass
class CaptureResult:
    lead: Lead
    created: bool
    matched_on: str | None = None  # "external_id" | "email" | "phone" when created is False
    conflicts: list[uuid.UUID] = field(default_factory=list)  # other leads that also match


def capture_lead(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    data: CaptureInput,
    actor_user_id: uuid.UUID | None = None,
) -> CaptureResult:
    _assert_tenant_context(db, tenant_id)
    clean = _validate(data)

    _lock_keys(db, tenant_id, clean)
    matches = _find_matches(db, tenant_id, clean)

    if matches:
        lead, matched_on = matches[0]
        conflicts = [m.id for m, _ in matches[1:]]
        _fill_blanks(lead, clean)
        created = False
    else:
        lead, created = _create(db, tenant_id, clean)
        matched_on, conflicts = None, []
        if not created:  # lost a race on (tenant, source, external_id)
            matches = _find_matches(db, tenant_id, clean)
            lead, matched_on = matches[0]
            conflicts = [m.id for m, _ in matches[1:]]

    db.add(
        Interaction(
            tenant_id=tenant_id,
            lead_id=lead.id,
            type=clean["interaction_type"],
            source=clean["source"],
            details=_details(clean, created, matched_on),
            created_by_user_id=actor_user_id,
        )
    )
    db.flush()
    db.refresh(lead)  # load server defaults (status, priority, version)

    if created:
        emit_lead_created(db, lead, actor_user_id)
    return CaptureResult(lead=lead, created=created, matched_on=matched_on, conflicts=conflicts)


def emit_lead_created(db: Session, lead: Lead, actor_user_id: uuid.UUID | None) -> None:
    """Hook: write a lead.created row to outbox_events inside this transaction.

    Not wired yet: the outbox model must exist first. Keep this call in the same
    transaction so the event exists only if the lead commits.
    """
    return None


# --- internals -------------------------------------------------------------


def _assert_tenant_context(db: Session, tenant_id: uuid.UUID) -> None:
    current = db.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()
    if (current or "").lower() != str(tenant_id).lower():
        raise CaptureError("tenant context is not set for this transaction")


def _text(value: str | None, max_len: int, label: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > max_len:
        raise CaptureError(f"{label} is too long (max {max_len})")
    return value


def _validate(data: CaptureInput) -> dict:
    try:
        name = clean_name(data.name)
        email = normalize_email(data.email)
        phone = normalize_phone(data.phone)
    except InvalidContact as exc:
        raise CaptureError(str(exc)) from exc
    if len(name) > 200:
        raise CaptureError("name is too long (max 200)")
    if not email and not phone:
        raise CaptureError("email or phone is required")
    if data.source not in VALID_SOURCES:
        raise CaptureError(f"unknown source: {data.source}")

    consent_source = data.consent_source
    if data.consent and consent_source is None:
        consent_source = DEFAULT_CONSENT_SOURCE.get(data.source, "api")
    if consent_source is not None and consent_source not in VALID_CONSENT_SOURCES:
        raise CaptureError(f"unknown consent source: {consent_source}")

    interaction_type = data.interaction_type or DEFAULT_INTERACTION.get(data.source, "note")
    if interaction_type not in VALID_INTERACTIONS:
        raise CaptureError(f"unknown interaction type: {interaction_type}")

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "company_name": _text(data.company_name, 200, "company_name"),
        "source": data.source,
        "source_campaign": _text(data.source_campaign, 200, "source_campaign"),
        "external_id": _text(data.external_id, 200, "external_id"),
        "consent": bool(data.consent),
        "consent_source": consent_source,
        "notes": _text(data.notes, 4000, "notes"),
        "interaction_type": interaction_type,
        "metadata": dict(data.interaction_metadata or {}),
        "assigned_user_id": data.assigned_user_id,
        "team_id": data.team_id,
    }


def _lock_keys(db: Session, tenant_id: uuid.UUID, clean: dict) -> None:
    """Serialize concurrent captures of the same contact (email/phone have no unique index)."""
    keys = []
    if clean["external_id"]:
        keys.append(f"{tenant_id}:ext:{clean['source']}:{clean['external_id']}")
    if clean["email"]:
        keys.append(f"{tenant_id}:email:{clean['email']}")
    if clean["phone"]:
        keys.append(f"{tenant_id}:phone:{clean['phone']}")
    for key in sorted(keys):  # same order everywhere, so no deadlocks
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


def _find_matches(db: Session, tenant_id: uuid.UUID, clean: dict) -> list[tuple[Lead, str]]:
    found: list[tuple[Lead, str]] = []
    seen: set[uuid.UUID] = set()
    base = select(Lead).where(Lead.tenant_id == tenant_id)

    def add(rows, how: str) -> None:
        for lead in rows:
            if lead.id not in seen:
                seen.add(lead.id)
                found.append((lead, how))

    if clean["external_id"]:
        add(
            db.scalars(
                base.where(Lead.source == clean["source"], Lead.external_id == clean["external_id"])
            ).all(),
            "external_id",
        )
    if clean["email"]:
        add(db.scalars(base.where(Lead.email == clean["email"]).order_by(Lead.created_at)), "email")
    if clean["phone"]:
        add(db.scalars(base.where(Lead.phone == clean["phone"]).order_by(Lead.created_at)), "phone")
    return found


def _create(db: Session, tenant_id: uuid.UUID, clean: dict) -> tuple[Lead, bool]:
    now = datetime.now(UTC)
    lead = Lead(
        tenant_id=tenant_id,
        name=clean["name"],
        email=clean["email"],
        phone=clean["phone"],
        company_name=clean["company_name"],
        source=clean["source"],
        source_campaign=clean["source_campaign"],
        external_id=clean["external_id"],
        consent=clean["consent"],
        consent_at=now if clean["consent"] else None,
        consent_source=clean["consent_source"] if clean["consent"] else None,
        assigned_user_id=clean["assigned_user_id"],
        team_id=clean["team_id"],
    )
    try:
        with db.begin_nested():  # savepoint: a unique violation must not poison the transaction
            db.add(lead)
            db.flush()
    except IntegrityError:
        if clean["external_id"] and _find_matches(db, tenant_id, clean):
            return lead, False
        raise
    return lead, True


def _fill_blanks(lead: Lead, clean: dict) -> None:
    """A repeat capture adds information; it never overwrites or downgrades."""
    changed = False
    for attr in ("company_name", "email", "phone", "source_campaign"):
        if clean[attr] and not getattr(lead, attr):
            setattr(lead, attr, clean[attr])
            changed = True
    if clean["consent"] and not lead.consent:
        lead.consent = True
        lead.consent_at = datetime.now(UTC)
        lead.consent_source = clean["consent_source"]
        changed = True
    if changed:
        lead.version += 1


def _details(clean: dict, created: bool, matched_on: str | None) -> dict:
    details = dict(clean["metadata"])
    details.update({"captured_via": clean["source"], "created": created, "matched_on": matched_on})
    if clean["source_campaign"]:
        details["campaign"] = clean["source_campaign"]
    if clean["notes"]:
        details["text"] = clean["notes"]
    return details
