import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.modules.ai.provider import (
    OPENAI_CHAT_COMPLETIONS_URL,
    AIProviderError,
    analyze_with_openai,
)


def test_openai_analysis_uses_json_mode_and_validates_summary_and_sentiment(monkeypatch):
    client = MagicMock()
    response = client.post.return_value
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "summary": "Customer wants a demo.",
                            "sentiment": "positive",
                            "confidence": 0.9,
                        }
                    )
                }
            }
        ]
    }
    client.__enter__.return_value = client
    client_options = {}

    def create_client(**kwargs):
        client_options.update(kwargs)
        return client

    monkeypatch.setattr("app.modules.ai.provider.httpx.Client", create_client)

    result = analyze_with_openai(
        {"system": "instructions", "user": "redacted messages"},
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=5,
    )

    assert result.summary == "Customer wants a demo."
    assert result.sentiment == "positive"
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    assert args == (OPENAI_CHAT_COMPLETIONS_URL,)
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == "gpt-test"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}
    assert client_options["timeout"] == 5


def test_openai_analysis_rejects_missing_required_fields(monkeypatch):
    client = MagicMock()
    response = client.post.return_value
    response.json.return_value = {
        "choices": [{"message": {"content": '{"summary":"Missing sentiment"}'}}]
    }
    client.__enter__.return_value = client
    monkeypatch.setattr("app.modules.ai.provider.httpx.Client", lambda **kwargs: client)

    with pytest.raises(AIProviderError, match="invalid conversation analysis"):
        analyze_with_openai(
            {"system": "instructions", "user": "messages"},
            api_key="test-key",
            model="gpt-test",
            timeout_seconds=5,
        )


def test_openai_analysis_hides_provider_error_details(monkeypatch):
    client = MagicMock()
    request = httpx.Request("POST", OPENAI_CHAT_COMPLETIONS_URL)
    response = httpx.Response(500, request=request, text="sensitive provider response")
    client.post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "sensitive provider response", request=request, response=response
    )
    client.__enter__.return_value = client
    monkeypatch.setattr("app.modules.ai.provider.httpx.Client", lambda **kwargs: client)

    with pytest.raises(AIProviderError, match="request failed") as exc:
        analyze_with_openai(
            {"system": "instructions", "user": "messages"},
            api_key="test-key",
            model="gpt-test",
            timeout_seconds=5,
        )

    assert "sensitive provider response" not in str(exc.value)
