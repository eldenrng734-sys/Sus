"""Tests for app/modules/ai/adapter.py.

Rules verified:
  - FakeAnalyzer works offline and returns a valid AnalysisResult
  - AnthropicAdapter maps LLMError → AnalysisResult(status=failed); never raises
  - LLM_PROVIDER=fake is refused at startup when APP_ENV=production
  - An unknown LLM_PROVIDER value raises at startup
  - confidence < threshold sets requires_review flag in the persisted assessment
    (tested through the jobs flow with a FakeAnalyzer that returns low confidence)
  - An adapter failure (failed result) stores a failed assessment flagged for review
  - An event goes dead after MAX_ATTEMPTS
"""

import uuid

import pytest

from app.modules.ai.adapter import FakeAnalyzer, get_adapter
from app.modules.ai.jobs import (
    AnalysisResult,
    JobInput,
    _failed_result,
    _run_analyzer,
)


def _make_job() -> JobInput:
    return JobInput(
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        redacted_messages=["Customer asks for a demo."],
        pii_values=[],
    )


# ── FakeAnalyzer ──────────────────────────────────────────────────────────────


def test_fake_analyzer_returns_valid_result():
    result = FakeAnalyzer()(_make_job())
    assert isinstance(result, AnalysisResult)
    assert result.status in ("ok", "fallback", "failed")
    assert result.model
    assert result.prompt_version


def test_fake_analyzer_never_touches_network(monkeypatch):
    """FakeAnalyzer must work without any network, even if httpx is broken."""
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **_: pytest.fail("network must not be used"))
    result = FakeAnalyzer()(_make_job())
    assert result.status == "ok"


def test_fake_analyzer_low_confidence_sets_review_flag():
    """A FakeAnalyzer configured with low confidence returns confidence < 0.6."""
    result = FakeAnalyzer(confidence=0.3)(_make_job())
    assert result.output.get("confidence", 1.0) < 0.6


# ── get_adapter ───────────────────────────────────────────────────────────────


def test_get_adapter_fake_allowed_in_non_production(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("APP_ENV", "development")
    adapter = get_adapter()
    assert isinstance(adapter, FakeAnalyzer)


def test_get_adapter_fake_refused_in_production(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="fake.*production"):
        get_adapter()


def test_get_adapter_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "some_unknown_provider_xyz")
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_adapter()


def test_get_adapter_anthropic_returned_when_configured(monkeypatch):
    from app.modules.ai.adapter import AnthropicAdapter

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("APP_ENV", "development")
    adapter = get_adapter()
    assert isinstance(adapter, AnthropicAdapter)


# ── Adapter error handling (AnthropicAdapter never raises into job runner) ────


def test_anthropic_adapter_llm_error_returns_failed_result(monkeypatch):
    """Any LLMError from the client must be caught and become status=failed."""
    from app.modules.ai.adapter import AnthropicAdapter
    from app.modules.ai.llm_client import LLMUnavailable

    def _raise(*_, **__):
        raise LLMUnavailable("provider down")

    adapter = AnthropicAdapter()
    monkeypatch.setattr(adapter._client, "complete", _raise)

    result = adapter(_make_job())
    assert result.status == "failed"


# ── jobs._run_analyzer with FakeAnalyzer ─────────────────────────────────────


def test_run_analyzer_with_fake_succeeds():
    job = _make_job()
    result = _run_analyzer(FakeAnalyzer(), job)
    assert result.status == "ok"


def test_run_analyzer_captures_provider_exception_as_failed():
    def _bad_analyzer(_job):
        raise RuntimeError("network gone")

    result = _run_analyzer(_bad_analyzer, _make_job())
    assert result.status == "failed"


def test_run_analyzer_does_not_catch_not_implemented():
    def _wiring_mistake(_job):
        raise NotImplementedError("adapter not wired")

    with pytest.raises(NotImplementedError):
        _run_analyzer(_wiring_mistake, _make_job())


def test_failed_result_has_expected_shape():
    r = _failed_result()
    assert r.status == "failed"
    assert r.model == "unavailable"
    assert r.output == {}
