from unittest.mock import MagicMock

import pytest

from app.modules.audit.service import record_audit_event


def test_record_audit_event_adds_event():
    session = MagicMock()

    event = record_audit_event(
        session,
        action="auth.login",
        actor_type="user",
        request_id="request-123",
        details={"source": "web"},
    )

    assert event.action == "auth.login"
    assert event.actor_type == "user"
    assert event.request_id == "request-123"
    assert event.details == {"source": "web"}

    session.add.assert_called_once_with(event)
    session.commit.assert_not_called()


def test_record_audit_event_supports_system_actor():
    session = MagicMock()

    event = record_audit_event(
        session,
        action="system.cleanup",
        actor_type="system",
    )

    assert event.actor_type == "system"
    assert event.details == {}


def test_record_audit_event_rejects_invalid_actor_type():
    session = MagicMock()

    with pytest.raises(ValueError, match="Invalid audit actor_type"):
        record_audit_event(
            session,
            action="test.action",
            actor_type="invalid",
        )

    session.add.assert_not_called()
