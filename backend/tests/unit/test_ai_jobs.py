import uuid

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.modules.ai import jobs
from app.modules.ai.provider import AIProviderError
from app.modules.ai.service import ConversationAnalysisOutput


def test_default_analyzer_uses_configured_provider_and_prompt(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "openai_model", "test-model")
    monkeypatch.setattr(settings, "openai_timeout_seconds", 7.0)
    job = jobs.JobInput(
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        redacted_messages=["Customer: [REDACTED] asks for a demo"],
        pii_values=["Ayesha"],
    )
    received = {}

    def analyze(prompt, **kwargs):
        received["prompt"] = prompt
        received["kwargs"] = kwargs
        return ConversationAnalysisOutput(
            summary="Customer requested a demo.",
            sentiment="positive",
            confidence=0.9,
        )

    monkeypatch.setattr(jobs, "analyze_with_openai", analyze)

    result = jobs.default_analyzer(job)

    assert result.status == "ok"
    assert result.model == "test-model"
    assert result.prompt_version == jobs.PROMPT_VERSION
    assert result.output["summary"] == "Customer requested a demo."
    assert "Ayesha" not in received["prompt"]["user"]
    assert received["kwargs"] == {
        "api_key": "test-api-key",
        "model": "test-model",
        "timeout_seconds": 7.0,
    }


def test_default_analyzer_fails_closed_when_provider_is_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(
        jobs,
        "analyze_with_openai",
        lambda *args, **kwargs: pytest.fail("provider must not be called"),
    )
    job = jobs.JobInput(
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        redacted_messages=["Need a demo"],
        pii_values=[],
    )

    with pytest.raises(AIProviderError, match="not configured"):
        jobs.default_analyzer(job)
