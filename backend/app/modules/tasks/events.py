"""Task domain events producer (#8).

Produces transactional outbox events for follow-up task lifecycle:
- task.due: follow-up created or approved, scheduled at available_at = due_at
- task.cancelled: follow-up cancelled, rejected, paused, completed, or rescheduled

Cancelling or replacing a task cancels any existing pending task.due row
in outbox_events to optimize n8n queueing. The true safety check remains
at send time (#9).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.outbox import enqueue_event

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.modules.tasks.models import Task

_CANCEL_PENDING_TASK_DUE = text(
    """
    UPDATE outbox_events
       SET status = 'dead', last_error = :reason
     WHERE tenant_id = :tenant_id
       AND aggregate_type = 'task'
       AND aggregate_id = :task_id
       AND event_type = 'task.due'
       AND status = 'pending'
    """
)


def cancel_pending_task_due(
    session: Session,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    reason: str = "cancelled",
) -> None:
    """Cancel any pending task.due event for this task."""
    session.execute(
        _CANCEL_PENDING_TASK_DUE,
        {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "reason": reason,
        },
    )


def emit_task_event(
    session: Session,
    event_type: str,
    task: Task,
    available_at: datetime | None = None,
) -> None:
    """Emit a task domain event to outbox_events for the n8n dispatcher.

    Args:
        session:      The current DB session.
        event_type:   'task.due' or 'task.cancelled'.
        task:         The Task ORM object that triggered the event.
        available_at: Optional override for when the task is due.
    """
    if event_type == "task.due":
        cancel_pending_task_due(session, task.tenant_id, task.id, reason="replaced")
        enqueue_event(
            session,
            tenant_id=task.tenant_id,
            event_type="task.due",
            aggregate_type="task",
            aggregate_id=task.id,
            idempotency_key=str(uuid.uuid4()),
            payload={
                "task_id": str(task.id),
                "lead_id": str(task.lead_id),
            },
            available_at=available_at or task.due_at,
        )
    elif event_type == "task.cancelled":
        cancel_pending_task_due(session, task.tenant_id, task.id, reason="cancelled")
        enqueue_event(
            session,
            tenant_id=task.tenant_id,
            event_type="task.cancelled",
            aggregate_type="task",
            aggregate_id=task.id,
            idempotency_key=str(uuid.uuid4()),
            payload={
                "task_id": str(task.id),
                "lead_id": str(task.lead_id),
            },
        )
    else:
        raise ValueError(f"Unknown task event_type: {event_type}")
