import uuid
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.invitations import service
from app.modules.invitations.schemas import AcceptRequest, ChangeRoleRequest, InviteRequest
from app.modules.tenants.models import TenantMembership

router = APIRouter(prefix="/api/v1", tags=["invitations"])


def current_admin(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_session),
) -> TenantMembership:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError(401, "unauthorized", "Missing access token")
    try:
        payload = decode_access_token(authorization[7:])
    except jwt.PyJWTError:
        raise AuthError(401, "unauthorized", "Invalid or expired token") from None
    return service.get_admin_membership(session, uuid.UUID(payload["sub"]))


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
