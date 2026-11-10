"""Tenant context: who is calling, and which company are they acting for.

Rules (API_CONTRACT 3.2, ARCHITECTURE 6):
- X-Tenant-ID is only a request. An active membership is verified every time.
- Verified ids are stored in the DB transaction with set_config(..., true).
- The access token carries no role or tenant; everything is loaded fresh.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, Header
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.auth.models import RefreshToken
from app.modules.tenants.models import Tenant, TenantMembership
from app.modules.users.models import User

USER_KEY = "app.user_id"
TENANT_KEY = "app.tenant_id"


def _set_context(session: Session, key: str, value: str) -> None:
    """Remember the value on the session AND set it in the current transaction."""
    session.info[key] = value
    session.execute(text("SELECT set_config(:k, :v, true)"), {"k": key, "v": value})


@event.listens_for(Session, "after_begin")
def _reapply_context(session, transaction, connection) -> None:
    """A commit ends the transaction and clears the setting. Re-apply it at every
    new transaction so later queries in the same request still carry the tenant.
    A session with no verified context sets nothing, so RLS denies by default."""
    for key in (USER_KEY, TENANT_KEY):
        value = session.info.get(key)
        if value:
            connection.execute(text("SELECT set_config(:k, :v, true)"), {"k": key, "v": value})


@dataclass(frozen=True)
class TenantContext:
    """Plain verified values (no ORM objects, so nothing expires after a commit)."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    membership_id: uuid.UUID
    role: str
    team_id: uuid.UUID | None
    session_id: uuid.UUID


def _claims(authorization: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError(401, "unauthorized", "Missing or invalid access token")
    try:
        payload = decode_access_token(authorization[7:].strip())
        return uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthError(401, "unauthorized", "Missing or invalid access token") from exc


def _check_user_and_session(session: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    # app.user_id lets the pre-tenant RLS policies find this user's own memberships.
    _set_context(session, USER_KEY, str(user_id))

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError(401, "unauthorized", "Missing or invalid access token")

    # sid = the refresh-token family. Logout or reuse detection revokes all of it.
    live = session.scalar(
        select(RefreshToken.id)
        .where(
            RefreshToken.family_id == session_id,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .limit(1)
    )
    if live is None:
        raise AuthError(401, "unauthorized", "Session is no longer valid")


def get_tenant_context(
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    session: Session = Depends(get_session),
) -> TenantContext:
    user_id, session_id = _claims(authorization)

    if not x_tenant_id:
        raise AuthError(400, "bad_request", "X-Tenant-ID header is required")
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise AuthError(400, "bad_request", "X-Tenant-ID must be a UUID") from exc

    _check_user_and_session(session, user_id, session_id)

    membership = session.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.is_active.is_(True),
        )
    )
    if membership is None:
        raise AuthError(403, "forbidden", "You do not have access to this company")

    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise AuthError(403, "forbidden", "You do not have access to this company")
    if tenant.status == "suspended":
        raise AuthError(403, "tenant_suspended", "This company is suspended")
    if tenant.status != "active":
        raise AuthError(403, "forbidden", "You do not have access to this company")

    context = TenantContext(
        user_id=user_id,
        tenant_id=tenant_id,
        membership_id=membership.id,
        role=membership.role,
        team_id=membership.team_id,
        session_id=session_id,
    )
    # Only now, after every check passed, is the tenant set for this request.
    _set_context(session, TENANT_KEY, str(tenant_id))
    return context
