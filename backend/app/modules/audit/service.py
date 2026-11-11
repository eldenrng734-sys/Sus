import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog


def record_audit_event(
    session: Session,
    *,
    action: str,
    actor_type: str,
    tenant_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit event to the caller's current transaction.

    The caller owns commit/rollback. Never store passwords, tokens,
    credentials, or customer message bodies in details.
    """

    allowed_actor_types = {
        "user",
        "system",
        "automation",
        "platform_admin",
    }

    if actor_type not in allowed_actor_types:
        raise ValueError("Invalid audit actor_type")

    event = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        details=details if details is not None else {},
    )

    session.add(event)
    return event
