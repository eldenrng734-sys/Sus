import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.modules.auth.errors import AuthError
from app.modules.integrations import webhooks
from app.modules.integrations.webhooks import extract_events


def _whatsapp_payload(messages=None, statuses=None, account="pn-1"):
    value = {
        "metadata": {
            "phone_number_id": account,
        }
    }

    if messages:
        value["messages"] = messages

    if statuses:
        value["statuses"] = statuses

    return {
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": value,
                    }
                ],
            }
        ]
    }


def test_whatsapp_message_and_status_ids():
    payload = _whatsapp_payload(
        messages=[{"id": "wamid.1"}],
        statuses=[{"id": "wamid.1", "status": "read"}],
    )

    events = extract_events("whatsapp", payload)

    assert [(event.event_id, event.event_type) for event in events] == [
        ("wamid.1", "message"),
        ("wamid.1:read", "status"),
    ]

    assert events[0].account_id == "pn-1"


def test_meta_messenger_uses_message_id():
    payload = {
        "entry": [
            {
                "id": "page-9",
                "messaging": [
                    {
                        "message": {
                            "mid": "m.1",
                        }
                    }
                ],
            }
        ]
    }

    events = extract_events("meta", payload)

    assert len(events) == 1
    assert events[0].account_id == "page-9"
    assert events[0].event_id == "m.1"
    assert events[0].event_type == "message"


def test_entry_without_account_is_ignored():
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": "message-1"}]}}]}]}

    assert extract_events("whatsapp", payload) == []


@pytest.mark.parametrize(
    "bad_payload",
    [
        [],
        {},
        {"entry": "invalid"},
        "invalid",
    ],
)
def test_malformed_payload_is_rejected(bad_payload):
    with pytest.raises(AuthError) as exc:
        extract_events("whatsapp", bad_payload)

    assert exc.value.status_code == 400


def _configure_receive(monkeypatch, session, insert_result):
    integration_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    session.scalar.return_value = insert_result
    monkeypatch.setattr(webhooks, "verify_signature", lambda *args: True)
    monkeypatch.setattr(
        webhooks,
        "_resolve_integration",
        lambda *_args: (integration_id, tenant_id),
    )
    return integration_id, tenant_id


def test_receive_publishes_new_message_after_commit_without_message_content(monkeypatch):
    session = MagicMock()
    _integration_id, tenant_id = _configure_receive(monkeypatch, session, uuid.uuid4())
    published = []

    def publish(name, payload):
        assert session.commit.call_count == 1
        published.append((name, payload))

    monkeypatch.setattr(webhooks.event_emitter, "publish", publish)
    payload = _whatsapp_payload(
        messages=[{"id": "wamid.1", "text": {"body": "private customer message"}}]
    )

    result = webhooks.receive(
        session,
        "whatsapp",
        json.dumps(payload).encode(),
        "valid-signature",
    )

    assert result == {"stored": 1, "duplicates": 0}
    assert len(published) == 1
    event_name, event_payload = published[0]
    assert event_name.value == "message.received"
    assert event_payload["tenant_id"] == tenant_id
    assert event_payload["message_id"] == "wamid.1"
    assert event_payload["provider"] == "whatsapp"
    assert event_payload["occurred_at"].tzinfo is not None
    assert set(event_payload) == {"tenant_id", "message_id", "provider", "occurred_at"}


def test_receive_does_not_publish_duplicate_message(monkeypatch):
    session = MagicMock()
    _configure_receive(monkeypatch, session, None)
    publish = MagicMock()
    monkeypatch.setattr(webhooks.event_emitter, "publish", publish)

    result = webhooks.receive(
        session,
        "whatsapp",
        json.dumps(_whatsapp_payload(messages=[{"id": "wamid.1"}])).encode(),
        "valid-signature",
    )

    assert result == {"stored": 0, "duplicates": 1}
    publish.assert_not_called()


def test_receive_does_not_publish_when_commit_fails(monkeypatch):
    session = MagicMock()
    _configure_receive(monkeypatch, session, uuid.uuid4())
    session.commit.side_effect = RuntimeError("commit failed")
    publish = MagicMock()
    monkeypatch.setattr(webhooks.event_emitter, "publish", publish)

    with pytest.raises(RuntimeError, match="commit failed"):
        webhooks.receive(
            session,
            "whatsapp",
            json.dumps(_whatsapp_payload(messages=[{"id": "wamid.1"}])).encode(),
            "valid-signature",
        )

    session.rollback.assert_called_once()
    publish.assert_not_called()
