import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Interaction, Lead

OPT_OUT_KEYWORDS = {
    "stop",
    "stop all",
    "unsubscribe",
    "cancel",
    "end",
    "quit",
    "opt out",
    "optout",
    "বন্ধ",
    "বন্ধ করুন",
}


def normalize(text: str) -> str:
    """Normalize customer messages before checking keywords."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = "".join(
        character
        for character in text
        if not unicodedata.category(character).startswith(("P", "S"))
    )
    return " ".join(text.split())


def is_opt_out_message(text: str) -> bool:
    """Return True only when the entire message is an opt-out command."""
    return normalize(text) in OPT_OUT_KEYWORDS


def can_message(lead: Lead) -> tuple[bool, str | None]:
    """Return whether outbound messaging is allowed for this lead."""
    if lead.opted_out:
        return False, "opt_out"
    if not lead.consent:
        return False, "no_consent"
    return True, None


def apply_opt_out(
    session: Session,
    lead_id: uuid.UUID,
    source: str,
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    """Opt a lead out and cancel open automated follow-ups in one transaction.

    Returns False when the lead was already opted out. The caller must have set
    the verified tenant context on the session before invoking this function.
    """
    if not source or len(source) > 50:
        raise ValueError("source must contain between 1 and 50 characters")

    lead = session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")
    if lead.opted_out:
        return False

    import app.database.registry  # noqa: F401
    from app.modules.tasks.models import Task

    try:
        lead.opted_out = True
        lead.opted_out_at = datetime.now(UTC)
        lead.opted_out_source = source
        lead.version += 1

        session.execute(
            update(Task)
            .where(
                Task.tenant_id == lead.tenant_id,
                Task.lead_id == lead.id,
                Task.type == "follow_up",
                Task.created_by == "automation",
                Task.status == "open",
            )
            .values(
                status="cancelled",
                version=Task.version + 1,
                updated_at=func.now(),
            )
        )

        session.add(
            Interaction(
                tenant_id=lead.tenant_id,
                lead_id=lead.id,
                type="opt_out",
                source=source,
                details={"source": source},
                created_by_user_id=actor_user_id,
            )
        )
        record_audit_event(
            session,
            action="lead.opted_out",
            actor_type=(
                "user"
                if actor_user_id
                else "automation"
                if source in {"whatsapp", "messenger"}
                else "system"
            ),
            tenant_id=lead.tenant_id,
            actor_user_id=actor_user_id,
            entity_type="lead",
            entity_id=lead.id,
            details={"source": source},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return True
