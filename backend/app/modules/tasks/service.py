from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.idempotency import claim_idempotency, store_idempotency_response
from app.core.permissions import apply_data_scope
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Interaction, Lead
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.modules.ai.models import LeadAssessment
    from app.modules.tasks.models import Task

CREATE_TASK_PATH = "/api/v1/tasks"

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


def _add_timeline(session, task, event_type: str, actor_user_id=None, details: dict | None = None):
    """Write an Interaction (lead timeline) entry for a task event."""
    session.add(
        Interaction(
            tenant_id=task.tenant_id,
            lead_id=task.lead_id,
            type=event_type,
            source="task",
            details={
                "task_id": str(task.id),
                "task_title": task.title,
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                **(details or {}),
            },
        )
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
            User.id == TenantMembership.user_id,
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


def _task_request_hash(body) -> str:
    """Stable hash of the task creation body for idempotency."""
    normalized = body.model_dump(mode="json")
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def list_tasks(session, context, limit: int = 50, offset: int = 0):
    Task = _task_model()
    statement = apply_data_scope(select(Task), Task, context)
    statement = (
        statement.order_by(Task.due_at.asc(), Task.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .offset(max(offset, 0))
    )
    return list(session.scalars(statement).all())


def list_due_follow_ups(session, context, due_before: str | None = None, limit: int = 50):
    """Return open follow_up tasks where due_at <= due_before (default: now), scoped."""
    Task = _task_model()
    if due_before is not None:
        try:
            cutoff = datetime.fromisoformat(due_before.rstrip("Z"))
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=UTC)
        except (ValueError, AttributeError):
            msg = "due_before must be a valid ISO-8601 datetime"
            raise AuthError(422, "invalid_param", msg) from None
    else:
        cutoff = datetime.now(UTC)

    statement = apply_data_scope(select(Task), Task, context).where(
        Task.type == "follow_up",
        Task.status == "open",
        Task.due_at <= cutoff,
    )
    statement = statement.order_by(Task.due_at.asc()).limit(min(max(limit, 1), 100))
    return list(session.scalars(statement).all())


def get_task(session, context, task_id):
    return _get_scoped_task(session, context, task_id)


def create_task(session, context, body, idempotency_key: str):
    """Create a task; return (task, is_replay).

    Idempotency: a duplicate key with the same body replays the original task.
    """
    Task = _task_model()
    request_hash = _task_request_hash(body)

    try:
        idempotency_id, replay_body = claim_idempotency(
            session,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            path=CREATE_TASK_PATH,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay_body is not None:
            # Return the previously-created task.
            task_id = replay_body.get("id")
            task = session.scalar(
                select(Task).where(
                    Task.tenant_id == context.tenant_id,
                    Task.id == task_id,
                )
            )
            if task is None:
                raise AuthError(500, "internal_error", "Replayed task could not be reloaded")
            return task, True

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

        if task.type == "follow_up" and not task.requires_approval:
            from app.modules.tasks.events import emit_task_event

            emit_task_event(session, "task.due", task, available_at=task.due_at)

        response_body = {"id": str(task.id)}
        store_idempotency_response(session, idempotency_id, response_body)

        session.commit()
        session.refresh(task)
        return task, False
    except Exception:
        session.rollback()
        raise


def update_task(session, context, task_id, body):
    try:
        task = _get_scoped_task(session, context, task_id, for_update=True)
        changes = body.model_dump(exclude_unset=True)

        # Optimistic version lock: client must send the version it last read.
        if "version" in changes:
            if changes["version"] != task.version:
                raise AuthError(
                    409,
                    "version_conflict",
                    "Task was modified by another request; reload and retry",
                )
            changes = {k: v for k, v in changes.items() if k != "version"}

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
        _add_timeline(
            session,
            task,
            "task_updated",
            actor_user_id=context.user_id,
            details={"fields": list(changes)},
        )

        from app.modules.tasks.events import emit_task_event

        if changes.get("status") in ("done", "cancelled", "paused"):
            emit_task_event(session, "task.cancelled", task)
        elif changes.get("status") == "open":
            if task.type == "follow_up" and task.approval_status in ("not_required", "approved"):
                available_at = max(datetime.now(UTC), task.due_at)
                emit_task_event(session, "task.due", task, available_at=available_at)
        elif "due_at" in changes and task.status == "open":
            if task.type == "follow_up" and task.approval_status in ("not_required", "approved"):
                emit_task_event(session, "task.due", task, available_at=task.due_at)

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

        from app.modules.tasks.events import emit_task_event

        if approved:
            available_at = max(now, task.due_at)
            emit_task_event(session, "task.due", task, available_at=available_at)
        else:
            emit_task_event(session, "task.cancelled", task)

        session.commit()
        session.refresh(task)
        return task
    except Exception:
        session.rollback()
        raise


def pause_followups(
    session: Session,
    lead_id: uuid.UUID,
    reason: str = "customer_reply",
) -> list[Task]:
    """Pause open follow_up tasks for a lead upon customer reply.

    Call, meeting and reminder tasks are untouched.
    Writes a timeline entry for each paused task.
    """
    Task = _task_model()
    statement = select(Task).where(
        Task.lead_id == lead_id,
        Task.type == "follow_up",
        Task.status == "open",
    )
    tasks = list(session.scalars(statement).all())
    from app.modules.tasks.events import emit_task_event

    for task in tasks:
        task.status = "paused"
        task.version += 1
        _add_timeline(
            session,
            task,
            "task_paused",
            actor_user_id=None,
            details={"reason": reason},
        )
        emit_task_event(session, "task.cancelled", task)

    return tasks


def cancel_followups(
    session: Session,
    lead_id: uuid.UUID,
    reason: str = "opt_out",
) -> list[Task]:
    """Cancel open and paused follow_up tasks for a lead upon opt-out.

    Call, meeting and reminder tasks are untouched.
    Writes a timeline entry for each cancelled task.
    """
    Task = _task_model()
    statement = select(Task).where(
        Task.lead_id == lead_id,
        Task.type == "follow_up",
        Task.status.in_(["open", "paused"]),
    )
    tasks = list(session.scalars(statement).all())
    from app.modules.tasks.events import emit_task_event

    for task in tasks:
        task.status = "cancelled"
        task.version += 1
        _add_timeline(
            session,
            task,
            "task_cancelled",
            actor_user_id=None,
            details={"reason": reason},
        )
        emit_task_event(session, "task.cancelled", task)

    return tasks


def create_assessment_follow_up(
    session,
    assessment: "LeadAssessment",
    lead: Lead,
) -> "Task | None":
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

    from sqlalchemy.dialects.postgresql import insert

    from app.database import registry

    task_model = registry.Task

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
