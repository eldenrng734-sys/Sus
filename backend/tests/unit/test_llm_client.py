import json
import logging

import httpx
import pytest

from app.modules.ai.llm_client import (
    LLMBadResponse,
    LLMClient,
    LLMNotConfigured,
    LLMRejected,
    LLMTimeout,
    LLMUnavailable,
)

OK = {
    "content": [{"type": "text", "text": '{"intent": "pricing"}'}],
    "model": "test-model",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 100, "output_tokens": 20},
}


def make_client(handler):
    sleeps: list[float] = []
    client = LLMClient(
        api_key="test-key",
        model="test-model",
        base_url="https://llm.test/v1/messages",
        timeout=5,
        max_retries=2,
        input_price_per_mtok=1.0,
        output_price_per_mtok=5.0,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )
    return client, sleeps


def call(client):
    return client.complete(system="SYS", user="CUSTOMER SECRET TEXT", purpose="test")


def test_success_returns_text_tokens_and_cost():
    client, _ = make_client(lambda request: httpx.Response(200, json=OK))
    result = call(client)
    assert result.text == '{"intent": "pricing"}'
    assert (result.input_tokens, result.output_tokens, result.attempts) == (100, 20, 1)
    assert result.cost_usd == pytest.approx((100 * 1.0 + 20 * 5.0) / 1_000_000)
    assert result.truncated is False


def test_request_has_the_right_shape():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK)

    client, _ = make_client(handler)
    call(client)
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["system"] == "SYS"
    assert seen["body"]["messages"] == [{"role": "user", "content": "CUSTOMER SECRET TEXT"}]
    assert seen["body"]["max_tokens"] == 512
    assert "temperature" not in seen["body"]


def test_retries_overload_then_succeeds():
    responses = [httpx.Response(529), httpx.Response(200, json=OK)]
    client, sleeps = make_client(lambda request: responses.pop(0))
    result = call(client)
    assert result.attempts == 2
    assert len(sleeps) == 1


def test_gives_up_after_max_retries():
    count = {"n": 0}

    def handler(request):
        count["n"] += 1
        return httpx.Response(503)

    client, _ = make_client(handler)
    with pytest.raises(LLMUnavailable):
        call(client)
    assert count["n"] == 3  # first try + 2 retries


def test_bad_key_is_not_retried():
    count = {"n": 0}

    def handler(request):
        count["n"] += 1
        return httpx.Response(401, json={"error": {"type": "authentication_error"}})

    client, _ = make_client(handler)
    with pytest.raises(LLMRejected):
        call(client)
    assert count["n"] == 1


def test_timeout_is_retried_then_raised():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    client, sleeps = make_client(handler)
    with pytest.raises(LLMTimeout):
        call(client)
    assert len(sleeps) == 2


def test_empty_answer_is_rejected():
    client, _ = make_client(lambda request: httpx.Response(200, json={"content": [], "usage": {}}))
    with pytest.raises(LLMBadResponse):
        call(client)


def test_missing_key_is_reported():
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    client = LLMClient(api_key="", model="", http=http)
    with pytest.raises(LLMNotConfigured):
        call(client)


def test_logs_never_contain_prompt_or_answer_text(caplog):
    caplog.set_level(logging.INFO, logger="app.llm")
    client, _ = make_client(lambda request: httpx.Response(200, json=OK))
    call(client)
    assert "llm_call" in caplog.text
    assert "CUSTOMER SECRET TEXT" not in caplog.text
    assert "pricing" not in caplog.text
    assert "test-key" not in caplog.text
