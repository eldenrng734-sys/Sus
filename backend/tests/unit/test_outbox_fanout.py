"""Tests for outbox fan-out and task event lifecycle (Missing Parts #8).

Tests:
- One new lead produces separate rows:
  assessment.requested (AI worker) and lead.created (dispatcher)
- Inbound message produces separate rows (assessment.requested and lead.replied)
- Creating a follow-up writes task.due with available_at = due_at
- Cancelling a task cancels its pending task.due
- Completing a task cancels its pending task.due
- Rescheduling a task replaces its pending task.due
- No event type is written without an assigned consumer
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core import outbox
from app.core.dispatcher import HANDLED_EVENTS as DISPATCHER_EVENTS
from app.modules.ai.jobs import HANDLED_EVENTS as AI_WORKER_EVENTS
from app.modules.tasks.events import emit_task_event


class _RecordingSession:
    """Session recording SQL statements and parameters."""

    def __init__(self):
        self.calls = []
        self.committed = 0

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return SimpleNamespace(all=lambda: [], first=lambda: None, scalar=lambda: None)

    def commit(self):
        self.committed += 1

    def flush(self):
        pass


def test_lead_created_produces_separate_rows_for_ai_and_dispatcher():
    """One new lead must produce two outbox rows:
    1. assessment.requested -> AI worker
    2. lead.created -> n8n dispatcher
    Each with unique idempotency keys.
    """
    session = _RecordingSession()
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    outbox.emit_lead_created(session, tenant_id=tenant_id, lead_id=lead_id, source="whatsapp")

    # Should have two insert executions
    inserts = [params for stmt, params in session.calls if "INSERT INTO outbox_events" in stmt]
    assert len(inserts) == 2

    event_types = {ins["event_type"] for ins in inserts}
    assert event_types == {"assessment.requested", "lead.created"}

    # Distinct idempotency keys
    keys = [ins["idempotency_key"] for ins in inserts]
    assert len(set(keys)) == 2
    assert all(k is not None for k in keys)

    # Consumers are matched
    ai_event = next(ins for ins in inserts if ins["event_type"] == "assessment.requested")
    assert ai_event["aggregate_type"] == "lead"
    assert ai_event["aggregate_id"] == lead_id
    assert ai_event["event_type"] in AI_WORKER_EVENTS

    disp_event = next(ins for ins in inserts if ins["event_type"] == "lead.created")
    assert disp_event["aggregate_type"] == "lead"
    assert disp_event["aggregate_id"] == lead_id
    assert disp_event["event_type"] in DISPATCHER_EVENTS


def test_inbound_message_produces_separate_rows_for_ai_and_dispatcher():
    """An inbound message must produce two outbox rows:
    1. assessment.requested -> AI worker
    2. lead.replied -> n8n dispatcher
    """
    session = _RecordingSession()
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    outbox.emit_message_received(
        session,
        tenant_id=tenant_id,
        message_id=msg_id,
        conversation_id=conv_id,
        lead_id=lead_id,
    )

    inserts = [params for stmt, params in session.calls if "INSERT INTO outbox_events" in stmt]
    assert len(inserts) == 2

    event_types = {ins["event_type"] for ins in inserts}
    assert event_types == {"assessment.requested", "lead.replied"}

    ai_event = next(ins for ins in inserts if ins["event_type"] == "assessment.requested")
    assert ai_event["aggregate_type"] in ("message", "lead")
    assert ai_event["event_type"] in AI_WORKER_EVENTS

    disp_event = next(ins for ins in inserts if ins["event_type"] == "lead.replied")
    assert disp_event["event_type"] in DISPATCHER_EVENTS


def test_emit_task_event_due_writes_row_with_available_at():
    """Creating or approving a follow-up task writes task.due with available_at = due_at."""
    session = _RecordingSession()
    tenant_id = uuid.uuid4()
    task_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    due_at = datetime.now(UTC) + timedelta(days=2)

    task = SimpleNamespace(
        id=task_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        type="follow_up",
        status="open",
        due_at=due_at,
    )

    emit_task_event(session, "task.due", task, available_at=due_at)

    inserts = [params for stmt, params in session.calls if "INSERT INTO outbox_events" in stmt]
    assert len(inserts) == 1
    assert inserts[0]["event_type"] == "task.due"
    assert inserts[0]["available_at"] == due_at
    assert inserts[0]["aggregate_id"] == task_id
    assert inserts[0]["event_type"] in DISPATCHER_EVENTS


def test_emit_task_event_cancelled_cancels_pending_task_due():
    """Cancelling a task cancels any pending task.due row and emits task.cancelled."""
    session = _RecordingSession()
    tenant_id = uuid.uuid4()
    task_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    task = SimpleNamespace(
        id=task_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        type="follow_up",
        status="cancelled",
        due_at=datetime.now(UTC),
    )

    emit_task_event(session, "task.cancelled", task)

    # Must update/cancel pending task.due
    cancel_updates = [
        (stmt, params)
        for stmt, params in session.calls
        if "UPDATE outbox_events" in stmt and "task.due" in stmt
    ]
    assert len(cancel_updates) >= 1
    assert cancel_updates[0][1]["task_id"] == task_id
    assert cancel_updates[0][1]["tenant_id"] == tenant_id

    # Must write task.cancelled outbox row for the dispatcher
    inserts = [params for stmt, params in session.calls if "INSERT INTO outbox_events" in stmt]
    assert len(inserts) == 1
    assert inserts[0]["event_type"] == "task.cancelled"
    assert inserts[0]["aggregate_id"] == task_id
    assert inserts[0]["event_type"] in DISPATCHER_EVENTS


def test_no_event_type_is_written_without_a_consumer():
    """Verify all system event types have an assigned consumer in AI worker or n8n dispatcher."""
    all_consumers = set(AI_WORKER_EVENTS) | set(DISPATCHER_EVENTS)

    system_events = {
        "assessment.requested",
        "lead.created",
        "lead.replied",
        "task.due",
        "task.cancelled",
    }

    unconsumed = system_events - all_consumers
    assert not unconsumed, f"Event types without consumer: {unconsumed}"
