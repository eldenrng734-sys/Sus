import pytest

from app.modules.auth.errors import AuthError
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
