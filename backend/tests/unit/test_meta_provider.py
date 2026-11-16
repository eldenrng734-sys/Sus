"""Unit tests for the Meta Page webhook provider and Graph helpers."""

import asyncio
import uuid
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from app.modules.auth.errors import AuthError
from app.modules.integrations.meta import (
    MetaGraphError,
    MetaProvider,
    extract_lead_fields,
    fetch_lead,
    subscribe_page,
)

PAGE_ID = "123456789012345"


def _leadgen_payload(leadgen_id: str = "987654321") -> dict:
    return {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "time": 1_700_000_000_000,
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": leadgen_id,
                            "page_id": PAGE_ID,
                            "form_id": "form-1",
                            "ad_id": "ad-1",
                        },
                    }
                ],
            }
        ],
    }


def test_leadgen_change_becomes_leadgen_event():
    events = MetaProvider().parse(_leadgen_payload())

    assert len(events) == 1
    event = events[0]
    assert event.account_id == PAGE_ID
    assert event.event_id == "987654321"
    assert event.event_type == "leadgen"
    assert event.data == {"leadgen_id": "987654321", "page_id": PAGE_ID}


def test_messenger_message_becomes_message_event():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [
                    {
                        "sender": {"id": "customer-psid"},
                        "recipient": {"id": PAGE_ID},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "m.123", "text": "Hello"},
                    }
                ],
            }
        ],
    }

    events = MetaProvider().parse(payload)

    assert len(events) == 1
    assert events[0].account_id == PAGE_ID
    assert events[0].event_id == "m.123"
    assert events[0].event_type == "message"
    assert events[0].data["messaging"]["message"]["text"] == "Hello"


def test_echo_delivery_read_and_postback_are_ignored():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [
                    # Echo of our own outbound message
                    {
                        "sender": {"id": PAGE_ID},
                        "message": {"mid": "echo-1", "is_echo": True, "text": "sent"},
                    },
                    # Delivery and read receipts
                    {"sender": {"id": "customer"}, "delivery": {"mids": ["m.1"]}},
                    {"sender": {"id": "customer"}, "read": {"watermark": 1}},
                    # Postback without a message object
                    {"sender": {"id": "customer"}, "postback": {"payload": "GET_STARTED"}},
                ],
            }
        ],
    }

    assert MetaProvider().parse(payload) == []


def test_message_echo_flag_is_ignored_even_with_different_sender():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [
                    {
                        "sender": {"id": "some-other-page"},
                        "message": {"mid": "echo-2", "is_echo": True, "text": "sent"},
                    }
                ],
            }
        ],
    }

    assert MetaProvider().parse(payload) == []


def test_non_page_object_is_rejected():
    payload = _leadgen_payload()
    payload["object"] = "whatsapp_business_account"

    with pytest.raises(AuthError) as exc:
        MetaProvider().parse(payload)

    assert exc.value.status_code == 400
    assert exc.value.code == "malformed_payload"


def test_missing_entry_list_is_rejected():
    with pytest.raises(AuthError) as exc:
        MetaProvider().parse({"object": "page", "entry": {}})

    assert exc.value.status_code == 400


def test_entries_without_page_id_are_skipped():
    payload = {
        "object": "page",
        "entry": [
            {"changes": [{"field": "leadgen", "value": {"leadgen_id": str(uuid.uuid4().int)}}]}
        ],
    }

    assert MetaProvider().parse(payload) == []


def test_extract_lead_fields_keeps_unknown_fields_and_first_value():
    fields = extract_lead_fields(
        {
            "field_data": [
                {"name": "full_name", "values": ["Ayesha Rahman", "ignored"]},
                {"name": "email", "values": ["ayesha@example.com"]},
                {"name": "custom_question", "values": ["Need 20 seats"]},
                {"name": "empty", "values": []},
                {"name": "", "values": ["x"]},
            ]
        }
    )

    assert fields == {
        "full_name": "Ayesha Rahman",
        "email": "ayesha@example.com",
        "custom_question": "Need 20 seats",
    }


def test_subscribe_page_sends_required_fields_and_header():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        route = mock.post(path__regex=rf"^/v\d+\.\d+/{PAGE_ID}/subscribed_apps$").respond(
            200, json={"success": True}
        )

        asyncio.run(subscribe_page(PAGE_ID, "page-token"))

    assert route.called
    request = route.calls[0].request
    form = parse_qs(request.content.decode())
    assert form == {"subscribed_fields": ["leadgen,messages,messaging_postbacks"]}
    assert request.headers["authorization"] == "Bearer page-token"
    assert "access_token" not in str(request.url)


def test_subscribe_page_rejects_non_numeric_page_id():
    with pytest.raises(AuthError) as exc:
        asyncio.run(subscribe_page("../evil", "page-token"))

    assert exc.value.status_code == 400


def test_subscribe_page_surfaces_provider_rejection_as_502():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        mock.post(path__regex=r"^/.*").respond(
            403,
            json={"error": {"code": 200, "message": "permission denied"}},
        )

        with pytest.raises(AuthError) as exc:
            asyncio.run(subscribe_page(PAGE_ID, "page-token"))

    assert exc.value.status_code == 502
    assert "page-token" not in exc.value.message


def test_fetch_lead_requests_only_required_fields_with_bearer_token():
    leadgen_id = "987654321"
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        route = mock.get(path__regex=rf"^/v\d+\.\d+/{leadgen_id}$").respond(
            200,
            json={"field_data": [{"name": "email", "values": ["a@example.com"]}]},
        )

        payload = asyncio.run(fetch_lead(leadgen_id, "page-token"))

    assert payload["field_data"][0]["name"] == "email"
    request = route.calls[0].request
    assert request.url.params["fields"] == "field_data,ad_id,form_id"
    assert "access_token" not in str(request.url)
    assert request.headers["authorization"] == "Bearer page-token"


def test_fetch_lead_rejects_provider_error_without_leaking_token():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        mock.get(path__regex=r"^/.*").respond(
            400,
            json={"error": {"code": 190, "message": "Invalid OAuth access token"}},
        )

        with pytest.raises(MetaGraphError) as exc:
            asyncio.run(fetch_lead("987654321", "super-secret-token"))

    assert "super-secret-token" not in str(exc.value)
    assert exc.value.status_code == 400


def test_fetch_lead_rejects_non_numeric_id():
    with pytest.raises(MetaGraphError):
        asyncio.run(fetch_lead("../../me", "page-token"))


def test_network_error_is_reported_as_safe_label():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        mock.get(path__regex=r"^/.*").mock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(MetaGraphError) as exc:
            asyncio.run(fetch_lead("987654321", "page-token"))

    assert exc.value.safe_label() == "graph_network_error"
    assert "page-token" not in str(exc.value)
