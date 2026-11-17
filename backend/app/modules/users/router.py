from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member, require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.users import service
from app.modules.users.schemas import UserProfileUpdate

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
def get_me(
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.get_current_user(session, context)}


@router.patch("/me")
def patch_me(
    body: UserProfileUpdate,
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.update_current_user(session, context, body)}


@router.get("")
def get_users(
    context: TenantContext = Depends(require_manager_or_admin),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.list_tenant_users(session, context)}
