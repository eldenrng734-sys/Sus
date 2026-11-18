"""Shared idempotency helpers for POST endpoints.

Usage pattern:
    idempotency_id, replay_body = claim_idempotency(session, ctx, key, path, request_hash)
    if replay_body is not None:
        return replay_body, True          # replay the previous response
    # ... do real work ...
    store_idempotency_response(session, idempotency_id, response_body)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.auth.errors import AuthError
from app.modules.idempotency.models import IdempotencyKey

IDEMPOTENCY_TTL = timedelta(hours=24)


def claim_idempotency(
    session: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | str,
    path: str,
    key: str,
    request_hash: str,
    caller_type: str = "user",
    method: str = "POST",
) -> tuple[uuid.UUID | None, dict[str, Any] | None]:
    """Claim an idempotency key, or return the previously stored response.

    Returns (claimed_id, None) when this is a new request, or
    (None, response_body) when the key was already used successfully.
    Raises AuthError 409 on hash mismatch or in-progress collision.
    """
    now = datetime.now(UTC)
    caller_id = str(user_id)
    statement = (
        pg_insert(IdempotencyKey)
        .values(
            tenant_id=tenant_id,
            caller_type=caller_type,
            caller_id=caller_id,
            method=method,
            path=path,
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
        return claimed_id, None

    existing = session.scalar(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.tenant_id == tenant_id,
            IdempotencyKey.caller_type == caller_type,
            IdempotencyKey.caller_id == caller_id,
            IdempotencyKey.method == method,
            IdempotencyKey.path == path,
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
    return None, existing.response_body


def store_idempotency_response(
    session: Session,
    idempotency_id: uuid.UUID,
    response_body: dict[str, Any],
    response_status: int = 201,
) -> None:
    """Persist the response so future duplicate requests replay it."""
    encoded = json.dumps(response_body, separators=(",", ":"), default=str).encode("utf-8")
    if len(encoded) > 64 * 1024:
        raise AuthError(500, "internal_error", "Idempotent response exceeded the storage limit")
    session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.id == idempotency_id)
        .values(response_status=response_status, response_body=response_body)
    )
