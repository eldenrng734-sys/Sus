from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import TaskApprovalOut, TaskApprovalRequest

if TYPE_CHECKING:
    from app.modules.ai.models import LeadAssessment
    from app.modules.leads.models import Lead


_FOLLOW_UP_ACTIONS = {
    "call": ("Call lead", "call", 1),
    "schedule_demo": ("Schedule a demo", "meeting", 0),
    "email": ("Email lead", "follow_up", 1),
    "follow_up": ("Follow up with lead", "follow_up", 2),
    "support": ("Follow up on support request", "follow_up", 1),
}


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

    statement = (
        insert(Task)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[Task.tenant_id, Task.idempotency_key],
            index_where=Task.idempotency_key.is_not(None),
        )
    )
    session.execute(statement)

    task = session.scalar(
        select(Task).where(
            Task.tenant_id == assessment.tenant_id,
            Task.idempotency_key == idempotency_key,
        )
    )

    if task is None:
        raise RuntimeError("Assessment follow-up task could not be loaded after insert")

    return task


def review_task_approval(
    session: Session,
    context: TenantContext,
    task_id: uuid.UUID,
    body: TaskApprovalRequest,
) -> TaskApprovalOut:
    """Approve or reject a task within the caller's permitted data scope."""
    statement = select(Task).where(
        Task.tenant_id == context.tenant_id,
        Task.id == task_id,
    )
    statement = apply_data_scope(statement, Task, context).with_for_update()

    task = session.scalar(statement)

    if task is None:
        raise AuthError(404, "not_found", "Task not found")

    if not task.requires_approval or task.approval_status != "pending":
        raise AuthError(409, "conflict", "Task is not awaiting approval")

    now = datetime.now(UTC)
    task.approval_note = body.note.strip() if body.note else None

    if body.decision == "approved":
        task.approval_status = "approved"
        task.approved_by_user_id = context.user_id
        task.approved_at = now
        task.rejected_by_user_id = None
        task.rejected_at = None
    else:
        task.approval_status = "rejected"
        task.rejected_by_user_id = context.user_id
        task.rejected_at = now
        task.approved_by_user_id = None
        task.approved_at = None

    session.commit()
    session.refresh(task)

    return TaskApprovalOut.model_validate(task)
