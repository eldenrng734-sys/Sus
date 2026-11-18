"""Unit tests for requeue_dead.py script (#14)."""

import uuid
from unittest.mock import MagicMock

from scripts.requeue_dead import list_dead_events, requeue_dead_event


def test_list_dead_events_formats_results():
    mock_session = MagicMock()
    r1 = MagicMock(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event_type="task.due",
        attempts=5,
        last_error="HTTPError",
        created_at="2026-11-18 00:00:00",
    )
    mock_session.execute.return_value.all.return_value = [r1]

    events = list_dead_events(mock_session)
    assert len(events) == 1
    assert events[0]["id"] == str(r1.id)
    assert events[0]["tenant_id"] == str(r1.tenant_id)
    assert events[0]["event_type"] == "task.due"
    assert events[0]["attempts"] == 5
    assert events[0]["last_error"] == "HTTPError"


def test_requeue_dead_event_resets_status_and_audits():
    mock_session = MagicMock()
    ev_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    row = MagicMock(
        id=ev_id,
        tenant_id=tenant_id,
        event_type="lead.replied",
        attempts=5,
        last_error="ConnectTimeout",
    )
    mock_session.execute.return_value.first.return_value = row

    res = requeue_dead_event(mock_session, ev_id, tenant_id=tenant_id)

    assert res is not None
    assert res["id"] == str(ev_id)
    assert res["status"] == "pending"
    assert res["previous_attempts"] == 5
    assert res["last_error"] == "ConnectTimeout"

    # Confirm commit and update called
    mock_session.commit.assert_called_once()
    assert mock_session.execute.call_count >= 2


def test_requeue_dead_event_returns_none_if_not_found():
    mock_session = MagicMock()
    mock_session.execute.return_value.first.return_value = None

    res = requeue_dead_event(mock_session, uuid.uuid4())
    assert res is None
    mock_session.commit.assert_not_called()
