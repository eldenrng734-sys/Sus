import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.auth.errors import AuthError
from app.modules.integrations import webhooks
from app.modules.integrations.protocols import ParsedEvent
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
    event = ParsedEvent(
        account_id="pn-1",
        event_id="wamid.1",
        event_type="message",
        data={"message": {"text": {"body": "private customer message"}}},
    )
    provider = SimpleNamespace(
        verify_signature=lambda *_args: True,
        parse=lambda _payload: [event],
        handle=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        webhooks,
        "get_provider",
        lambda *_args: provider,
    )
    monkeypatch.setattr(
        webhooks,
        "_resolve_integration",
        lambda *_args: (tenant_id, integration_id),
    )
    monkeypatch.setattr(
        webhooks,
        "record_event",
        MagicMock(return_value=insert_result),
    )
    return integration_id, tenant_id, event, provider


def test_receive_runs_deferred_provider_job_only_after_commit(monkeypatch):
    session = MagicMock()
    integration_id, tenant_id, event, provider = _configure_receive(
        monkeypatch, session, uuid.uuid4()
    )
    jobs = []

    async def after_commit_job():
        assert session.commit.call_count == 1
        jobs.append(True)

    provider.handle.return_value = [after_commit_job]

    result = asyncio.run(
        webhooks.receive(
            session,
            "whatsapp",
            json.dumps(_whatsapp_payload()).encode(),
            "valid-signature",
        )
    )

    assert result == {"stored": 1, "duplicates": 0, "skipped": 0}
    assert jobs == [True]
    provider.handle.assert_awaited_once_with(
        event,
        session,
        tenant_id,
        integration_id,
        webhooks.record_event.return_value,
    )


def test_receive_skips_duplicate_event_without_calling_provider(monkeypatch):
    session = MagicMock()
    _integration_id, _tenant_id, _event, provider = _configure_receive(monkeypatch, session, None)

    result = asyncio.run(
        webhooks.receive(
            session,
            "whatsapp",
            json.dumps(_whatsapp_payload()).encode(),
            "valid-signature",
        )
    )

    assert result == {"stored": 0, "duplicates": 1, "skipped": 0}
    provider.handle.assert_not_awaited()


def test_receive_does_not_run_deferred_job_when_commit_fails(monkeypatch):
    session = MagicMock()
    _integration_id, _tenant_id, _event, provider = _configure_receive(
        monkeypatch, session, uuid.uuid4()
    )
    session.commit.side_effect = RuntimeError("commit failed")
    job = AsyncMock()
    provider.handle.return_value = [job]

    with pytest.raises(RuntimeError, match="commit failed"):
        asyncio.run(
            webhooks.receive(
                session,
                "whatsapp",
                json.dumps(_whatsapp_payload()).encode(),
                "valid-signature",
            )
        )

    session.rollback.assert_called_once()
    job.assert_not_awaited()
