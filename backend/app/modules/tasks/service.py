
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.permissions import apply_data_scope
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Lead
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User

if TYPE_CHECKING:
    from app.core.permissions import TenantContext
    from app.modules.ai.models import LeadAssessment
    from app.modules.tasks.models import Task

_FOLLOW_UP_ACTIONS = {
    "call": ("Call lead", "call", 1),
    "schedule_demo": ("Schedule a demo", "meeting", 0),
    "email": ("Email lead", "follow_up", 1),
    "follow_up": ("Follow up with lead", "follow_up", 2),
    "support": ("Follow up on support request", "follow_up", 1),
}


def _task_model():
    # Resolve dynamically to avoid a registry/model circular import.
    from app.database import registry

    return registry.Task


def _audit(session, context, action: str, task, details: dict | None = None):
    record_audit_event(
        session,
        action=action,
        actor_type="user",
        tenant_id=context.tenant_id,
        actor_user_id=context.user_id,
        entity_type="task",
        entity_id=task.id,
        details=details or {},
    )


def _get_scoped_task(session, context, task_id, *, for_update=False):
    Task = _task_model()
    statement = select(Task).where(Task.id == task_id)
    statement = apply_data_scope(statement, Task, context)
    if for_update:
        statement = statement.with_for_update()

    task = session.scalar(statement)
    if task is None:
        raise AuthError(404, "not_found", "Task not found")
    return task


def _get_scoped_lead(session, context, lead_id):
    statement = select(Lead).where(Lead.id == lead_id)
    statement = apply_data_scope(statement, Lead, context)
    lead = session.scalar(statement)
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")
    return lead


def _validate_assignee(session, context, lead, user_id):
    if context.role == "rep" and user_id != context.user_id:
        raise AuthError(403, "forbidden", "Representatives can only assign tasks to themselves")

    membership = session.scalar(
        select(TenantMembership)
        .join(
            User,
            (User.id == TenantMembership.user_id)
            & (User.tenant_id == TenantMembership.tenant_id),
        )
        .where(
            TenantMembership.tenant_id == context.tenant_id,
            TenantMembership.user_id == user_id,
            TenantMembership.is_active.is_(True),
            TenantMembership.team_id == lead.team_id,
            User.is_active.is_(True),
        )
    )
    if membership is None:
        raise AuthError(
            422,
            "invalid_assignee",
            "Assignee must be an active member of this tenant and the lead's team",
        )


def list_tasks(session, context, limit: int = 50, offset: int = 0):
    Task = _task_model()
    statement = apply_data_scope(select(Task), Task, context)
    statement = (
        statement.order_by(Task.due_at.asc(), Task.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .offset(max(offset, 0))
    )
    return list(session.scalars(statement).all())


def get_task(session, context, task_id):
    return _get_scoped_task(session, context, task_id)


def create_task(session, context, body):
    Task = _task_model()

    try:
        lead = _get_scoped_lead(session, context, body.lead_id)

        assignee_id = body.assigned_user_id
        if assignee_id is None and context.role == "rep":
            assignee_id = context.user_id
        elif assignee_id is None:
            assignee_id = lead.assigned_user_id

        if assignee_id is not None:
            _validate_assignee(session, context, lead, assignee_id)

        task = Task(
            tenant_id=context.tenant_id,
            lead_id=lead.id,
            title=body.title,
            notes=body.notes,
            type=body.type,
            status="open",
            due_at=body.due_at,
            assigned_user_id=assignee_id,
            team_id=lead.team_id,
            requires_approval=body.requires_approval,
            approval_status="pending" if body.requires_approval else "not_required",
            created_by="user",
            version=1,
        )
        session.add(task)
        session.flush()
        _audit(session, context, "task.created", task, {"lead_id": str(lead.id)})
        session.commit()
        session.refresh(task)
        return task
    except Exception:
        session.rollback()
        raise


def update_task(session, context, task_id, body):
    try:
        task = _get_scoped_task(session, context, task_id, for_update=True)
        changes = body.model_dump(exclude_unset=True)

        if "assigned_user_id" in changes and changes["assigned_user_id"] is not None:
            lead = _get_scoped_lead(session, context, task.lead_id)
            _validate_assignee(session, context, lead, changes["assigned_user_id"])

        if changes.get("status") == "done":
            if task.requires_approval and task.approval_status != "approved":
                raise AuthError(
                    409,
                    "approval_required",
                    "This task must be approved before it can be completed",
                )
            task.completed_at = datetime.now(UTC)
        elif "status" in changes:
            task.completed_at = None

        for field in ("title", "notes", "due_at", "status", "assigned_user_id"):
            if field in changes:
                setattr(task, field, changes[field])

        task.version += 1
        _audit(session, context, "task.updated", task, {"fields": list(changes)})
        session.commit()
        session.refresh(task)
        return task
    except Exception:
        session.rollback()
        raise


def list_approval_queue(session, context, limit: int = 50, offset: int = 0):
    if context.role not in ("manager", "admin"):
        raise AuthError(403, "forbidden", "Manager or admin access is required")

    Task = _task_model()
    statement = apply_data_scope(select(Task), Task, context).where(
        Task.requires_approval.is_(True),
        Task.approval_status == "pending",
    )
    statement = (
        statement.order_by(Task.created_at.asc())
        .limit(min(max(limit, 1), 100))
        .offset(max(offset, 0))
    )
    return list(session.scalars(statement).all())


def decide_task_approval(
    session,
    context,
    task_id,
    approved: bool,
    note: str | None = None,
):
    if context.role not in ("manager", "admin"):
        raise AuthError(403, "forbidden", "Manager or admin access is required")

    try:
        task = _get_scoped_task(session, context, task_id, for_update=True)

        if not task.requires_approval or task.approval_status != "pending":
            raise AuthError(
                409,
                "invalid_approval_state",
                "This task is not waiting for approval",
            )

        now = datetime.now(UTC)
        task.approval_note = note

        if approved:
            task.approval_status = "approved"
            task.approved_by_user_id = context.user_id
            task.approved_at = now
            task.rejected_by_user_id = None
            task.rejected_at = None
            action = "task.approved"
        else:
            task.approval_status = "rejected"
            task.rejected_by_user_id = context.user_id
            task.rejected_at = now
            task.approved_by_user_id = None
            task.approved_at = None
            action = "task.rejected"

        task.version += 1
        _audit(session, context, action, task, {"note": note})
        session.commit()
        session.refresh(task)
        return task
    except Exception:
        session.rollback()
        raise


def create_assessment_follow_up(
    session: Session,
    assessment: LeadAssessment,
    lead: Lead,
) -> Task | None:
    """Create one idempotent task for an actionable validated assessment."""
    action = assessment.recommended_action
    task_config = _FOLLOW_UP_ACTIONS.get(action or "")
    if task_config is None:
        return None

    title, task_type, default_days = task_config
    follow_up_days = assessment.follow_up_days
    due_at = datetime.now(UTC) + timedelta(
        days=default_days if follow_up_days is None else follow_up_days
    )
    idempotency_key = f"assessment:{assessment.id}:follow-up"
    values = {
        "tenant_id": assessment.tenant_id,
        "lead_id": lead.id,
        "title": title,
        "notes": f"Created from AI assessment {assessment.id}.",
        "type": task_type,
        "status": "open",
        "due_at": due_at,
        "assigned_user_id": lead.assigned_user_id,
        "team_id": lead.team_id,
        "requires_approval": False,
        "approval_status": "not_required",
        "created_by": "automation",
        "idempotency_key": idempotency_key,
    }

    from app.database import registry

    task_model = registry.Task

    from sqlalchemy.dialects.postgresql import insert

    statement = (
        insert(task_model)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[task_model.tenant_id, task_model.idempotency_key],
            index_where=task_model.idempotency_key.is_not(None),
        )
    )
    session.execute(statement)
    task = session.scalar(
        select(task_model).where(
            task_model.tenant_id == assessment.tenant_id,
            task_model.idempotency_key == idempotency_key,
        )
    )
    if task is None:
        raise RuntimeError("Assessment follow-up task could not be loaded after insert")
    return task
