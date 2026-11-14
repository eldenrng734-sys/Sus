from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.modules.ai.models import LeadAssessment
    from app.modules.leads.models import Lead
    from app.modules.tasks.models import Task

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
