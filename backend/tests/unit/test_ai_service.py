import uuid
from datetime import UTC, datetime
from math import nan
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.modules.ai import service as assessment_service
from app.modules.ai.models import LeadAssessment
from app.modules.ai.service import (
    PROMPT_VERSION,
    AssessmentOutput,
    build_assessment_prompt,
    persist_assessment,
    redact_pii,
)


@pytest.fixture(autouse=True)
def isolate_persistence_tests(monkeypatch):
    monkeypatch.setattr(
        assessment_service,
        "lock_lead_for_assessment",
        MagicMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(assessment_service, "apply_assessment_business_rules", MagicMock())


def test_redact_pii_masks_known_values_emails_and_phone_numbers():
    text = "Call Ayesha at +1 (415) 555-0199 or ayesha@example.com"

    redacted = redact_pii(text, ["Ayesha", "ayesha@example.com", "+1 (415) 555-0199"])

    assert "Ayesha" not in redacted
    assert "ayesha@example.com" not in redacted
    assert "555-0199" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_build_assessment_prompt_redacts_message_and_records_prompt_version():
    prompt = build_assessment_prompt(
        [
            "Please contact Ayesha at ayesha@example.com",
            "Ayesha can also be reached at 415-555-0199",
        ],
        pii_values=(value for value in ["Ayesha", "ayesha@example.com"]),
    )

    assert prompt["prompt_version"] == PROMPT_VERSION
    assert "Ayesha" not in prompt["user"]
    assert "ayesha@example.com" not in prompt["user"]
    assert "415-555-0199" not in prompt["user"]
    assert "untrusted data" in prompt["system"]


def test_persist_assessment_stores_versions_and_only_redacted_output():
    session = MagicMock()
    session.scalar.return_value = datetime.now(UTC)
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    assessment = persist_assessment(
        session,
        tenant_id=tenant_id,
        lead_id=lead_id,
        conversation_id=conversation_id,
        output=AssessmentOutput(
            intent="request_demo",
            sentiment="positive",
            confidence=0.4,
            summary="Ayesha asked for a demo; call +1 415 555 0199",
        ),
        model="  provider/model-v1  ",
        prompt_version=f" {PROMPT_VERSION} ",
        pii_values=["Ayesha"],
    )

    assert isinstance(assessment, LeadAssessment)
    assert assessment.model == "provider/model-v1"
    assert assessment.prompt_version == PROMPT_VERSION
    assert assessment.summary == "[REDACTED] asked for a demo; call [REDACTED_PHONE]"
    assert assessment.raw_output["summary"] == assessment.summary
    assert assessment.needs_human_review is True
    assert assessment.review_status == "pending"
    session.add.assert_called_once_with(assessment)
    session.flush.assert_called_once_with()


def test_persist_assessment_marks_provider_failure_for_review():
    session = MagicMock()
    session.scalar.return_value = datetime.now(UTC)

    assessment = persist_assessment(
        session,
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        output={},
        model="provider/model-v1",
        prompt_version=PROMPT_VERSION,
        pii_values=[],
        status="failed",
    )

    assert assessment.needs_human_review is True
    assert assessment.review_status == "pending"
    assert assessment.status == "failed"


@pytest.mark.parametrize(
    "values",
    [
        {"intent": "send_message"},
        {"lead_score": 101},
        {"unvalidated_text": "persist me"},
        {"confidence": nan},
    ],
)
def test_assessment_output_rejects_invalid_or_unexpected_values(values):
    with pytest.raises(ValidationError):
        AssessmentOutput.model_validate(values)


def test_persist_assessment_rejects_empty_success_output():
    with pytest.raises(ValueError, match="must contain an assessment value"):
        persist_assessment(
            MagicMock(),
            tenant_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            conversation_id=None,
            output={},
            model="provider/model-v1",
            prompt_version=PROMPT_VERSION,
            pii_values=[],
        )


@pytest.mark.parametrize(("model", "prompt_version"), [("", PROMPT_VERSION), ("model", "")])
def test_persist_assessment_requires_model_and_prompt_version(model, prompt_version):
    with pytest.raises(ValueError, match="model and prompt_version"):
        persist_assessment(
            MagicMock(),
            tenant_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            conversation_id=None,
            output={},
            model=model,
            prompt_version=prompt_version,
            pii_values=[],
        )
