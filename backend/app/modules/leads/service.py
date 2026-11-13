import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

<<<<<<< HEAD
=======
from app.core.permissions import apply_data_scope
>>>>>>> origin/dev
from app.core.tenancy import TenantContext
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Interaction, Lead
from app.modules.leads.schemas import LeadAssignRequest
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User


def assign_lead(
    session: Session,
    context: TenantContext,
    lead_id: uuid.UUID,
    body: LeadAssignRequest,
) -> dict:
<<<<<<< HEAD
    lead = session.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.tenant_id == context.tenant_id,
        )
    )
=======
    statement = apply_data_scope(
        select(Lead).where(Lead.id == lead_id),
        Lead,
        context,
    ).with_for_update()
    lead = session.scalar(statement)
>>>>>>> origin/dev

    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")

<<<<<<< HEAD
    if context.role == "manager" and lead.team_id != context.team_id:
        raise AuthError(403, "forbidden", "You can only assign leads in your team")

=======
>>>>>>> origin/dev
    membership = session.scalar(
        select(TenantMembership)
        .join(User, User.id == TenantMembership.user_id)
        .where(
            TenantMembership.tenant_id == context.tenant_id,
            TenantMembership.user_id == body.assigned_user_id,
            TenantMembership.is_active.is_(True),
            TenantMembership.team_id == body.team_id,
            User.is_active.is_(True),
        )
    )

    if membership is None:
        raise AuthError(
            422,
            "invalid_assignee",
            "Target user must be an active member of the selected team",
        )

    if context.role == "manager" and membership.team_id != context.team_id:
        raise AuthError(403, "forbidden", "You can only assign to your team members")

    old_assigned_user_id = lead.assigned_user_id
    old_team_id = lead.team_id

    try:
        lead.assigned_user_id = body.assigned_user_id
        lead.team_id = body.team_id

        session.add(
            Interaction(
                tenant_id=context.tenant_id,
                lead_id=lead.id,
<<<<<<< HEAD
                type="assignment",
=======
                type="assigned",
>>>>>>> origin/dev
                source="manual",
                details={
                    "old_assigned_user_id": (
                        str(old_assigned_user_id) if old_assigned_user_id else None
                    ),
                    "new_assigned_user_id": str(body.assigned_user_id),
                    "old_team_id": str(old_team_id) if old_team_id else None,
                    "new_team_id": str(body.team_id),
                    "actor_user_id": str(context.user_id),
                },
<<<<<<< HEAD
            )
        )
=======
                created_by_user_id=context.user_id,
            )
        )
        lead.version += 1
>>>>>>> origin/dev

        record_audit_event(
            session,
            action="lead.assigned",
            actor_type="user",
            tenant_id=context.tenant_id,
            actor_user_id=context.user_id,
            entity_type="lead",
            entity_id=lead.id,
            details={
                "assigned_user_id": str(body.assigned_user_id),
                "team_id": str(body.team_id),
            },
        )

        session.commit()
        session.refresh(lead)

    except Exception:
        session.rollback()
        raise

    return {
        "id": str(lead.id),
        "assigned_user_id": str(lead.assigned_user_id),
        "team_id": str(lead.team_id),
        "status": lead.status,
<<<<<<< HEAD
=======
        "version": lead.version,
>>>>>>> origin/dev
    }
