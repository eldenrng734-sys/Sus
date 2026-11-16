import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.invitations import service
from app.modules.invitations.schemas import AcceptRequest, ChangeRoleRequest, InviteRequest
from app.modules.tenants.models import TenantMembership

router = APIRouter(prefix="/api/v1", tags=["invitations"])


def current_admin(
    context: TenantContext = Depends(require_admin),
    session: Session = Depends(get_session),
) -> TenantMembership:
    membership = session.get(TenantMembership, context.membership_id)
    if (
        membership is None
        or not membership.is_active
        or membership.role != "admin"
        or membership.tenant_id != context.tenant_id
    ):
        raise AuthError(403, "forbidden", "Admin access required")
    return membership


@router.post("/invitations", status_code=201)
def invite(
    body: InviteRequest,
    admin: TenantMembership = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.create_invitation(session, admin, body)}


@router.post("/invitations/accept", status_code=201)
def accept(body: AcceptRequest, session: Session = Depends(get_session)) -> dict:
    return {"data": service.accept_invitation(session, body)}


@router.post("/memberships/{membership_id}/deactivate")
def deactivate(
    membership_id: uuid.UUID,
    admin: TenantMembership = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.deactivate_membership(session, admin, membership_id)}


@router.patch("/memberships/{membership_id}/role")
def update_role(
    membership_id: uuid.UUID,
    body: ChangeRoleRequest,
    admin: TenantMembership = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.change_role(session, admin, membership_id, body.role)}
