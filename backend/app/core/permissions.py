"""Role-based access control dependencies."""

import uuid
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Header
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.core import tenancy
from app.core.tenancy import TenantContext, get_tenant_context
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.users.models import User


@dataclass(frozen=True)
class PlatformAdminContext:
    """Verified identity for platform-level operations only."""
    user_id: uuid.UUID
    session_id: uuid.UUID


def require_roles(*allowed_roles: str) -> Callable:
    """Allow access only to users with one of the specified tenant roles."""
    if not allowed_roles:
        raise ValueError("At least one role must be specified")

    def dependency(
        context: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if context.role not in allowed_roles:
            raise AuthError(403, "forbidden", "You do not have permission")
        return context

    return dependency


def require_platform_admin(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_session),
) -> PlatformAdminContext:
    """Verify a platform admin without requiring tenant membership."""
    user_id, session_id = tenancy._claims(authorization)

    # Validates active user and live refresh-token session.
    # Sets only the authenticated user context, not a tenant context.
    tenancy._check_user_and_session(session, user_id, session_id)

    user = session.get(User, user_id)
    if user is None or not user.is_platform_admin:
        raise AuthError(403, "forbidden", "Platform admin access required")

    return PlatformAdminContext(
        user_id=user_id,
        session_id=session_id,
    )


require_admin = require_roles("admin")
require_manager_or_admin = require_roles("manager", "admin")
require_any_member = require_roles("rep", "manager", "admin")


def apply_data_scope(statement, model, context: TenantContext):
    """Restrict a SQLAlchemy statement to the caller's permitted records."""
    statement = statement.where(model.tenant_id == context.tenant_id)

    if context.role == "rep":
        return statement.where(model.assigned_user_id == context.user_id)

    if context.role == "manager":
        if context.team_id is None:
            return statement.where(false())
        return statement.where(model.team_id == context.team_id)

    if context.role == "admin":
        return statement

    raise AuthError(403, "forbidden", "You do not have permission")
