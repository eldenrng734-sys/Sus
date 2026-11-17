from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User
from app.modules.users.schemas import UserProfileUpdate


def _serialize_user(user: User, membership: TenantMembership) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.full_name,
        "role": membership.role,
        "team_id": str(membership.team_id) if membership.team_id else None,
        "is_active": membership.is_active and user.is_active,
    }


def get_current_user(session: Session, context: TenantContext) -> dict:
    user = session.get(User, context.user_id)
    membership = session.get(TenantMembership, context.membership_id)

    if (
        user is None
        or membership is None
        or not user.is_active
        or not membership.is_active
        or membership.tenant_id != context.tenant_id
    ):
        raise AuthError(404, "not_found", "User profile not found")

    return _serialize_user(user, membership)


def update_current_user(
    session: Session,
    context: TenantContext,
    body: UserProfileUpdate,
) -> dict:
    user = session.get(User, context.user_id)
    membership = session.get(TenantMembership, context.membership_id)

    if user is None or not user.is_active:
        raise AuthError(404, "not_found", "User profile not found")

    if (
        membership is None
        or not membership.is_active
        or membership.tenant_id != context.tenant_id
    ):
        raise AuthError(404, "not_found", "Membership not found")

    user.full_name = body.display_name
    session.commit()
    session.refresh(user)

    return _serialize_user(user, membership)


def list_tenant_users(session: Session, context: TenantContext) -> list[dict]:
    statement = (
        select(User, TenantMembership)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == context.tenant_id,
            TenantMembership.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.full_name, User.email)
    )

    rows = session.execute(statement).all()
    return [_serialize_user(user, membership) for user, membership in rows]
