import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.database.session import set_tenant_context
from app.modules.audit.models import AuditLog
from app.modules.auth.schemas import LoginRequest, SignupRequest
from app.modules.tenants.models import Tenant, TenantMembership
from app.modules.users.models import User


class AuthError(Exception):
    """An error the API turns into the standard error format."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def signup(session: Session, body: SignupRequest) -> dict:
    """Create the company and its first admin in ONE transaction. No tokens are issued."""
    if session.scalar(select(User.id).where(User.email == body.email)):
        raise AuthError(409, "email_exists", "An account with this email already exists")

    password_hash = hash_password(body.password)
    tenant_id = uuid.uuid4()

    try:
        # Tenant context first, so the rows pass RLS once it is switched on.
        set_tenant_context(session, str(tenant_id))

        user = User(email=body.email, full_name=body.full_name, password_hash=password_hash)
        session.add(user)
        session.flush()

        tenant = Tenant(id=tenant_id, name=body.company_name, slug=body.company_slug)
        session.add(tenant)
        session.flush()

        membership = TenantMembership(tenant_id=tenant_id, user_id=user.id, role="admin")
        session.add(membership)
        session.flush()

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_user_id=user.id,
                action="auth.signup",
                entity_type="tenant",
                entity_id=tenant_id,
                details={},
            )
        )
        session.flush()
        result = {
            "tenant": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug},
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "email_verified": False,
            },
            "membership": {"role": membership.role, "is_active": True},
        }
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "slug" in str(exc.orig).lower():
            raise AuthError(409, "slug_taken", "This company address is already taken") from exc
        raise AuthError(409, "email_exists", "An account with this email already exists") from exc

    return result


def login(session: Session, body: LoginRequest) -> dict:
    """Check the password and hand out a short-lived access token."""
    user = session.scalar(select(User).where(User.email == body.email))

    if user is None:
        # Same work as a real check, so timing does not reveal which emails exist.
        verify_password(body.password, DUMMY_PASSWORD_HASH)
        raise AuthError(401, "invalid_credentials", "Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise AuthError(401, "invalid_credentials", "Invalid email or password")

    if not user.is_active:
        raise AuthError(403, "account_disabled", "This account is disabled")

    if user.email_verified_at is None:
        raise AuthError(403, "email_not_verified", "Verify your email before logging in")

    # TODO (Dev 5, Day 3): audit login success/failure through the approved pre-tenant
    # path (auth_attempts table), because there is no tenant context at login.
    user.last_login_at = datetime.now(UTC)
    session.commit()

    # TODO: Dev 3 replaces this temporary session id with a real refresh-token session.
    token = create_access_token(user.id, uuid.uuid4())
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "email_verified": True,
        },
    }
