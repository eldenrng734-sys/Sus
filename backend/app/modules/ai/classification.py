"""Classify one customer message. Never raises: failures become a safe 'unknown' result."""

import json
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ai.llm_client import LLMClient, LLMError, get_llm_client
from app.modules.ai.prompts import (
    CLASSIFY_PROMPT_VERSION,
    CLASSIFY_SYSTEM_PROMPT,
    build_user_prompt,
)

logger = logging.getLogger("app.ai")

REVIEW_CONFIDENCE_THRESHOLD = 0.6  # below this a human must look (ARCHITECTURE.md section 8)
MAX_MESSAGE_CHARS = 4_000

# These values must match the CHECK constraints on lead_assessments.
Category = Literal["business_customer", "individual", "partner", "spam", "unknown"]
Intent = Literal["request_demo", "pricing", "support", "info", "complaint", "other", "unknown"]
BuyingStage = Literal["awareness", "consideration", "decision", "unknown"]
Action = Literal["call", "schedule_demo", "email", "follow_up", "support", "none"]
Status = Literal["ok", "fallback", "failed"]


class ClassificationOutput(BaseModel):
    """What the model must return. Anything else is rejected and becomes a fallback."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Category
    intent: Intent
    interest: str | None = Field(default=None, max_length=200)
    buying_stage: BuyingStage
    recommended_action: Action
    follow_up_days: int = Field(ge=0, le=365)
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class ClassificationOutcome:
    status: Status
    output: ClassificationOutput  # always present; all "unknown" on fallback
    needs_human_review: bool
    model: str | None
    prompt_version: str
    error_code: str | None = None


def _fallback(status: Status, error_code: str, model: str | None) -> ClassificationOutcome:
    logger.warning("classify_fallback status=%s code=%s", status, error_code)
    return ClassificationOutcome(
        status=status,
        output=ClassificationOutput(
            category="unknown",
            intent="unknown",
            interest=None,
            buying_stage="unknown",
            recommended_action="none",
            follow_up_days=0,
            confidence=0.0,
        ),
        needs_human_review=True,
        model=model,
        prompt_version=CLASSIFY_PROMPT_VERSION,
        error_code=error_code,
    )


def _extract_json(raw: str) -> dict:
    """Take the first {...} block, so a stray sentence or code fence does not matter."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(raw[start : end + 1])


def classify_message(text: str, *, client: LLMClient | None = None) -> ClassificationOutcome:
    """The text must already be redacted by the caller."""
    cleaned = (text or "").strip()[:MAX_MESSAGE_CHARS]
    if not cleaned:
        return _fallback("fallback", "empty_message", None)

    client = client or get_llm_client()
    try:
        result = client.complete(
            system=CLASSIFY_SYSTEM_PROMPT,
            user=build_user_prompt(cleaned),
            purpose="classify",
            max_tokens=300,
        )
    except LLMError as exc:
        return _fallback("failed", type(exc).__name__, getattr(client, "model", None) or None)

    if result.truncated:
        return _fallback("fallback", "truncated", result.model)
    try:
        output = ClassificationOutput.model_validate(_extract_json(result.text))
    except ValueError:  # bad JSON and pydantic validation errors both end up here
        return _fallback("fallback", "invalid_output", result.model)

    return ClassificationOutcome(
        status="ok",
        output=output,
        needs_human_review=output.confidence < REVIEW_CONFIDENCE_THRESHOLD,
        model=result.model,
        prompt_version=CLASSIFY_PROMPT_VERSION,
    )