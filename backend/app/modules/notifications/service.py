from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.service_auth import InternalServiceContext
from app.database.session import set_tenant_context
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Lead
from app.modules.notifications import crud
from app.modules.notifications.schemas import NotificationCreateRequest
from app.modules.tenants.models import Tenant, TenantMembership
from app.modules.users.models import User


def create_notification(
    session: Session,
    context: InternalServiceContext,
    request: NotificationCreateRequest,
) -> None:
    try:
        set_tenant_context(session, str(context.tenant_id))
        tenant = session.scalar(
            select(Tenant).where(Tenant.id == context.tenant_id).with_for_update()
        )
        if tenant is None:
            raise AuthError(404, "not_found", "Tenant not found")
        if tenant.status != "active":
            code = "tenant_suspended" if tenant.status == "suspended" else "forbidden"
            raise AuthError(403, code, "Tenant is not active")

        idempotency_id, is_replay = crud.claim_idempotency(
            session,
            tenant_id=context.tenant_id,
            service_id=context.service_id,
            key=context.idempotency_key,
            request_hash=context.body_sha256,
        )
        if is_replay:
            session.commit()
            return

        recipient = session.execute(
            select(TenantMembership, User)
            .join(User, User.id == TenantMembership.user_id)
            .where(
                TenantMembership.tenant_id == context.tenant_id,
                TenantMembership.user_id == request.user_id,
                TenantMembership.is_active.is_(True),
                TenantMembership.role == "rep",
                User.is_active.is_(True),
            )
            .with_for_update()
        ).first()
        if recipient is None:
            raise AuthError(403, "forbidden", "Recipient must be an active Rep in this tenant")
        membership, user = recipient
        if membership.role != "rep" or not membership.is_active or not user.is_active:
            raise AuthError(403, "forbidden", "Recipient must be an active Rep in this tenant")

        lead = session.scalar(
            select(Lead)
            .where(
                Lead.tenant_id == context.tenant_id,
                Lead.id == request.entity_id,
            )
            .with_for_update()
        )
        if lead is None:
            raise AuthError(404, "not_found", "Lead not found")
        if lead.assigned_user_id != request.user_id:
            raise AuthError(403, "forbidden", "Recipient does not own this lead")

        crud.create_notification(
            session,
            tenant_id=context.tenant_id,
            user_id=request.user_id,
            notification_type=request.type,
            title=request.title,
            body=request.body,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
        )
        if idempotency_id is None:
            raise RuntimeError("New idempotency claim did not return an ID")
        crud.store_accepted_response(session, idempotency_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
