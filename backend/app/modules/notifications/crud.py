import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.auth.errors import AuthError
from app.modules.idempotency.models import IdempotencyKey
from app.modules.notifications.models import Notification

IDEMPOTENCY_TTL = timedelta(hours=24)
NOTIFICATION_PATH = "/internal/v1/automation/notifications"


def claim_idempotency(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    service_id: str,
    key: str,
    request_hash: str,
) -> tuple[uuid.UUID | None, bool]:
    """Claim the existing shared idempotency key or report a completed replay."""
    now = datetime.now(UTC)
    statement = (
        pg_insert(IdempotencyKey)
        .values(
            tenant_id=tenant_id,
            caller_type="service",
            caller_id=service_id,
            method="POST",
            path=NOTIFICATION_PATH,
            key=key,
            request_hash=request_hash,
            expires_at=now + IDEMPOTENCY_TTL,
        )
        .on_conflict_do_update(
            constraint="uq_idempotency_keys_scope",
            set_={
                "request_hash": request_hash,
                "response_status": None,
                "response_body": None,
                "expires_at": now + IDEMPOTENCY_TTL,
            },
            where=IdempotencyKey.expires_at <= func.now(),
        )
        .returning(IdempotencyKey.id)
    )
    claimed_id = session.scalar(statement)
    if claimed_id is not None:
        return claimed_id, False

    existing = session.scalar(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.tenant_id == tenant_id,
            IdempotencyKey.caller_type == "service",
            IdempotencyKey.caller_id == service_id,
            IdempotencyKey.method == "POST",
            IdempotencyKey.path == NOTIFICATION_PATH,
            IdempotencyKey.key == key,
        )
        .with_for_update()
    )
    if existing is None:
        raise AuthError(409, "idempotency_conflict", "Could not claim this idempotency key")
    if existing.request_hash != request_hash:
        raise AuthError(
            409,
            "idempotency_conflict",
            "This idempotency key was already used with a different request",
        )
    if existing.response_status is None or existing.response_body is None:
        raise AuthError(
            409,
            "idempotency_in_progress",
            "A request with this idempotency key is still being processed",
        )
    return None, True


def create_notification(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_type: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: uuid.UUID,
) -> Notification:
    notification = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(notification)
    session.flush()
    return notification


def store_accepted_response(session: Session, idempotency_id: uuid.UUID) -> None:
    session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.id == idempotency_id)
        .values(response_status=202, response_body={})
    )
