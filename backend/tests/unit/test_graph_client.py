import asyncio
import json

import httpx
import pytest
import respx

from app.modules.messaging.graph_client import GraphAPIError, GraphClient, RetryableError

PHONE_NUMBER_ID = "phone-number-test"
MESSAGES_PATH = rf"^/v\d+\.\d+/{PHONE_NUMBER_ID}/messages$"


def _send(payload=None):
    async def run():
        async with GraphClient("test-token", PHONE_NUMBER_ID) as client:
            return await client.send_message(
                "+8801700000000",
                payload or {"type": "text", "text": {"body": "Hello"}},
            )

    return asyncio.run(run())


def test_send_message_returns_provider_id_and_sends_bearer_token():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        route = mock.post(path__regex=MESSAGES_PATH).mock(
            return_value=httpx.Response(200, json={"messages": [{"id": "wamid.123"}]})
        )

        assert _send() == "wamid.123"

        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer test-token"
        body = json.loads(request.content)
        assert body == {
            "to": "+8801700000000",
            "type": "text",
            "text": {"body": "Hello"},
        }


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_retryable_statuses_raise_retryable_error(status_code):
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        mock.post(path__regex=MESSAGES_PATH).mock(
            return_value=httpx.Response(status_code, json={"error": {"code": 2}})
        )

        with pytest.raises(RetryableError) as exc:
            _send()

    assert exc.value.status_code == status_code


def test_bad_request_is_permanent_and_never_retried():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        route = mock.post(path__regex=MESSAGES_PATH).mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": 100, "error_subcode": 2494010}},
            )
        )

        with pytest.raises(GraphAPIError) as exc:
            _send()

    assert exc.value.status_code == 400
    assert exc.value.error_code == "100:2494010"
    assert route.call_count == 1


def test_malformed_success_response_is_permanent():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        mock.post(path__regex=MESSAGES_PATH).mock(
            return_value=httpx.Response(200, json={"messages": []})
        )

        with pytest.raises(GraphAPIError) as exc:
            _send()

    assert exc.value.error_code == "invalid_response"


def test_recipient_must_be_e164_with_plus():
    with pytest.raises(ValueError):

        async def run():
            async with GraphClient("test-token", PHONE_NUMBER_ID) as client:
                await client.send_message("8801700000000", {"type": "text"})

        asyncio.run(run())
