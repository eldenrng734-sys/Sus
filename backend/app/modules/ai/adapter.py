"""Unified LLM adapter for the AI assessment pipeline.

One Protocol, one real implementation (Anthropic via llm_client.py),
and one FakeAnalyzer for tests and the CI worker.

Selection:
  LLM_PROVIDER=anthropic  → AnthropicAdapter  (default for production)
  LLM_PROVIDER=fake       → FakeAnalyzer      (refused when APP_ENV=production)

Rules (ARCHITECTURE.md §8):
  - Adapters NEVER raise into the job runner; any provider error returns
    AnalysisResult(status=failed).  The job runner then persists a failed
    assessment flagged for human review.
  - No prompt text, PII or keys are ever logged here.
  - The real client (llm_client.py) handles retries, backoff and cost logging.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol, runtime_checkable

from app.modules.ai.jobs import AnalysisResult, JobInput, _failed_result
from app.modules.ai.llm_client import LLMClient, LLMError, LLMNotConfigured
from app.modules.ai.service import (
    PROMPT_VERSION,
    AssessmentOutput,
    ConversationAnalysisOutput,
    build_assessment_prompt,
)

logger = logging.getLogger("app.ai.adapter")


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class Analyzer(Protocol):
    """Callable that takes a JobInput and returns an AnalysisResult.

    Must never raise.  Any error must be caught internally and returned as
    AnalysisResult(status='failed').
    """

    def __call__(self, job: JobInput) -> AnalysisResult: ...


# ── Anthropic adapter ─────────────────────────────────────────────────────────


class AnthropicAdapter:
    """Calls the Anthropic API through the existing LLMClient (llm_client.py).

    The client already handles retries, backoff, timeout and cost logging.
    This adapter only maps the prompt dict → LLMClient.complete() → AnalysisResult.
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        from app.modules.ai.llm_client import get_llm_client

        self._client = client or get_llm_client()

    def __call__(self, job: JobInput) -> AnalysisResult:
        try:
            prompt = build_assessment_prompt(job.redacted_messages, pii_values=job.pii_values)
            llm_result = self._client.complete(
                system=prompt["system"],
                user=prompt["user"],
                purpose="lead_assessment",
                max_tokens=512,
                temperature=0.1,
            )
            output = ConversationAnalysisOutput.model_validate(json.loads(llm_result.text))
            return AnalysisResult(
                output=output.model_dump(),
                model=llm_result.model,
                prompt_version=prompt["prompt_version"],
                status="ok",
            )
        except (LLMNotConfigured, LLMError) as exc:
            logger.warning(
                "adapter_llm_error lead=%s error=%s",
                job.lead_id,
                type(exc).__name__,
            )
            return _failed_result()
        except Exception as exc:
            logger.warning(
                "adapter_error lead=%s error=%s",
                job.lead_id,
                type(exc).__name__,
            )
            return _failed_result()


# ── Fake adapter (tests / CI only) ────────────────────────────────────────────


class FakeAnalyzer:
    """Deterministic analyzer for tests.  Never touches the network.

    Parameters
    ----------
    confidence:
        The confidence value to embed in the output.  Defaults to 0.9 (high).
        Set to a value below AI_REVIEW_CONFIDENCE_THRESHOLD (0.6) to trigger
        the requires_review path.
    status:
        One of 'ok', 'fallback', 'failed'.  Defaults to 'ok'.
    """

    MODEL = "fake-analyzer-v1"

    def __init__(
        self,
        confidence: float = 0.9,
        status: str = "ok",
    ) -> None:
        self._confidence = confidence
        self._status = status

    def __call__(self, job: JobInput) -> AnalysisResult:
        output = AssessmentOutput(
            category="business_customer",
            intent="request_demo",
            sentiment="positive",
            buying_stage="consideration",
            priority="medium",
            confidence=self._confidence,
            summary="Fake: customer requested a demo.",
            recommended_action="follow_up",
            follow_up_days=2,
        )
        return AnalysisResult(
            output=output.model_dump(),
            model=self.MODEL,
            prompt_version=PROMPT_VERSION,
            status=self._status,  # type: ignore[arg-type]
        )


# ── Factory ───────────────────────────────────────────────────────────────────


def get_adapter() -> Analyzer:
    """Return the adapter selected by the LLM_PROVIDER environment variable.

    Called once at worker startup; the result is passed to run_forever().

    Raises
    ------
    RuntimeError
        If LLM_PROVIDER=fake and APP_ENV=production.
    ValueError
        If LLM_PROVIDER is set to an unrecognised value.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower().strip()
    app_env = os.environ.get("APP_ENV", "development").lower().strip()

    if provider == "fake":
        if app_env == "production":
            raise RuntimeError(
                "LLM_PROVIDER=fake is not allowed when APP_ENV=production. "
                "Set LLM_PROVIDER=anthropic and configure LLM_API_KEY."
            )
        return FakeAnalyzer()

    if provider == "anthropic":
        return AnthropicAdapter()

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. "
        "Supported values: 'anthropic', 'fake' (non-production only)."
    )
