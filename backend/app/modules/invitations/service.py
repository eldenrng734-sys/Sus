import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import generate_refresh_token, hash_password, hash_refresh_token
from app.database.session import set_tenant_context
from app.modules.auth.errors import AuthError
from app.modules.invitations.models import Invitation
from app.modules.invitations.schemas import AcceptRequest, InviteRequest
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User

INVITE_EXPIRE_DAYS = 7


def get_admin_membership(session: Session, user_id: uuid.UUID) -> TenantMembership:
    """The user's active admin membership. Raises 403 if they are not an admin."""
    stmt = select(TenantMembership).where(
        TenantMembership.user_id == user_id,
        TenantMembership.is_active.is_(True),
        TenantMembership.role == "admin",
    )
    membership = session.scalars(stmt).first()
    if membership is None:
        raise AuthError(403, "forbidden", "Admin access required")
    set_tenant_context(session, str(membership.tenant_id))
    return membership


def create_invitation(session: Session, admin: TenantMembership, body: InviteRequest) -> dict:
    email = body.email.lower()
    now = datetime.now(UTC)

    already_member = session.scalars(
        select(TenantMembership)
        .join(User, User.id == TenantMembership.user_id)
        .where(TenantMembership.tenant_id == admin.tenant_id, User.email == email)
    ).first()
    if already_member:
        raise AuthError(409, "conflict", "This user is already in your company")

    pending = session.scalars(
        select(Invitation).where(
            Invitation.tenant_id == admin.tenant_id,
            Invitation.email == email,
            Invitation.status == "pending",
        )
    ).first()
    if pending:
        if pending.expires_at > now:
            raise AuthError(409, "conflict", "A pending invitation already exists")
        pending.status = "expired"
        session.flush()

    raw_token = generate_refresh_token()  # long random value
    invitation = Invitation(
        tenant_id=admin.tenant_id,
        invited_by_user_id=admin.user_id,
        email=email,
        role=body.role,
        token_hash=hash_refresh_token(raw_token),  # only the hash is stored
        expires_at=now + timedelta(days=INVITE_EXPIRE_DAYS),
    )
    session.add(invitation)
    session.commit()
    # TODO: send raw_token by email (Mailpit). For now it is returned so we can test.
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "expires_at": invitation.expires_at.isoformat(),
        "invite_token": raw_token,
    }


def accept_invitation(session: Session, body: AcceptRequest) -> dict:
    invitation = session.scalars(
        select(Invitation).where(Invitation.token_hash == hash_refresh_token(body.token))
    ).first()
    now = datetime.now(UTC)
    if invitation is None or invitation.status != "pending":
        raise AuthError(400, "invalid_invitation", "Invitation is invalid or already used")
    if invitation.expires_at <= now:
        invitation.status = "expired"
        session.commit()
        raise AuthError(400, "invalid_invitation", "Invitation has expired")

    set_tenant_context(session, str(invitation.tenant_id))

    user = session.scalars(select(User).where(User.email == invitation.email)).first()
    if user is None:
        if not body.password:
            raise AuthError(422, "validation_error", "Password is required for a new account")
        user = User(
            email=invitation.email,
            full_name=body.full_name,
            password_hash=hash_password(body.password),
            email_verified_at=now,  # they received the invite on this email
        )
        session.add(user)
        session.flush()

    exists = session.scalars(
        select(TenantMembership).where(
            TenantMembership.tenant_id == invitation.tenant_id,
            TenantMembership.user_id == user.id,
        )
    ).first()
    if exists:
        raise AuthError(409, "conflict", "You are already in this company")

    membership = TenantMembership(
        tenant_id=invitation.tenant_id,
        user_id=user.id,
        role=invitation.role,
    )
    session.add(membership)
    invitation.status = "accepted"
    invitation.accepted_at = now
    session.commit()
    return {
        "user_id": str(user.id),
        "tenant_id": str(invitation.tenant_id),
        "role": membership.role,
    }

def _get_member(session: Session, admin: TenantMembership, membership_id: uuid.UUID):
    member = session.scalars(
        select(TenantMembership).where(
            TenantMembership.id == membership_id,
            TenantMembership.tenant_id == admin.tenant_id,  # stay inside own company
        )
    ).first()
    if member is None:
        raise AuthError(404, "not_found", "Member not found")
    if member.id == admin.id:
        raise AuthError(400, "invalid_request", "You cannot change your own membership")
    return member


def deactivate_membership(
    session: Session,
    admin: TenantMembership,
    membership_id: uuid.UUID,
) -> dict:
    member = _get_member(session, admin, membership_id)
    member.is_active = False
    session.commit()
    return {"id": str(member.id), "is_active": member.is_active}


def change_role(
    session: Session,
    admin: TenantMembership,
    membership_id: uuid.UUID,
    role: str,
) -> dict:
    member = _get_member(session, admin, membership_id)
    member.role = role
    session.commit()
    return {"id": str(member.id), "role": member.role}