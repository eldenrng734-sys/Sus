import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.ai import rules
from app.modules.ai import service as assessment_service
from app.modules.ai.models import LeadAssessment
from app.modules.ai.service import AssessmentOutput, persist_assessment


@pytest.fixture(autouse=True)
def isolate_persistence_tests(monkeypatch):
    monkeypatch.setattr(
        assessment_service,
        "lock_lead_for_assessment",
        MagicMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(assessment_service, "apply_assessment_business_rules", MagicMock())


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {
                "intent": "request_demo",
                "buying_stage": "decision",
                "category": "business_customer",
                "sentiment": "positive",
                "confidence": 0.9,
                "lead_score": 0,
            },
            100,
        ),
        (
            {
                "intent": "pricing",
                "buying_stage": "consideration",
                "category": "partner",
                "sentiment": "neutral",
                "confidence": 0.75,
                "lead_score": 100,
            },
            74,
        ),
        (
            {
                "intent": "complaint",
                "sentiment": "negative",
                "confidence": 0.2,
                "lead_score": 100,
            },
            0,
        ),
    ],
)
def test_score_is_deterministic_bounded_and_ignores_model_score(values, expected):
    assessment = AssessmentOutput.model_validate(values)

    assert rules.calculate_lead_score(assessment) == expected
    assert 0 <= rules.calculate_lead_score(assessment) <= 100


def test_score_requires_at_least_one_sales_classification_signal():
    assessment = AssessmentOutput.model_validate(
        {"sentiment": "positive", "confidence": 0.95, "summary": "Conversation summary"}
    )

    assert rules.has_lead_scoring_signals(assessment) is False
    with pytest.raises(ValueError, match="lacks lead-scoring signals"):
        rules.calculate_lead_score(assessment)


@pytest.mark.parametrize(
    ("values", "status", "expected"),
    [
        ({"confidence": 0.59}, "ok", True),
        ({"confidence": 0.9}, "fallback", True),
        ({"confidence": 0.9, "category": "spam"}, "ok", True),
        ({"confidence": 0.9, "intent": "complaint"}, "ok", True),
        ({"confidence": 0.9, "sentiment": "negative"}, "ok", True),
        ({"confidence": 0.9, "intent": "request_demo"}, "ok", False),
    ],
)
def test_review_policy_handles_confidence_provider_and_risk_signals(values, status, expected):
    assessment = AssessmentOutput.model_validate(values)

    assert rules.requires_human_review(assessment, status) is expected


@pytest.mark.parametrize(
    ("values", "score", "review_required", "expected"),
    [
        ({"intent": "request_demo"}, 90, False, "high"),
        ({"intent": "pricing"}, 55, False, "medium"),
        ({"intent": "info"}, 39, False, "low"),
        ({"intent": "request_demo"}, 90, True, "medium"),
        ({"intent": "complaint"}, 90, True, "low"),
        ({"sentiment": "negative"}, 70, False, "low"),
    ],
)
def test_priority_is_score_based_and_caps_review_or_risky_cases(
    values, score, review_required, expected
):
    assessment = AssessmentOutput.model_validate(values)

    assert rules.determine_priority(assessment, score, review_required) == expected


def test_persist_assessment_replaces_model_score_and_priority():
    session = MagicMock()
    session.scalar.return_value = datetime.now(UTC)
    assessment = persist_assessment(
        session,
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        output={
            "intent": "request_demo",
            "buying_stage": "decision",
            "category": "business_customer",
            "sentiment": "positive",
            "confidence": 0.95,
            "lead_score": 1,
            "priority": "low",
            "summary": "Wants a demo",
        },
        model="test-model",
        prompt_version="test-prompt",
        pii_values=[],
    )

    assert assessment.lead_score == 100
    assert assessment.priority == "high"
    assert assessment.raw_output["lead_score"] == 100
    assert assessment.raw_output["priority"] == "high"
    assert assessment.needs_human_review is False
    assert assessment.review_status == "not_required"


def test_conversation_only_assessment_does_not_project_score_or_priority():
    session = MagicMock()
    assessment_time = datetime.now(UTC)
    session.scalar.return_value = assessment_time

    assessment = persist_assessment(
        session,
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        output={
            "sentiment": "positive",
            "confidence": 0.95,
            "summary": "Customer asked for information.",
        },
        model="test-model",
        prompt_version="conversation-v1",
        pii_values=[],
    )

    assert assessment.lead_score is None
    assert assessment.priority is None
    assert assessment.created_at == assessment_time


def test_assessment_review_risk_stays_pending_and_does_not_create_task(monkeypatch):
    assessment = LeadAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        status="ok",
        needs_human_review=True,
        review_status="pending",
        lead_score=90,
        priority="low",
        recommended_action="call",
    )
    lead = SimpleNamespace(
        id=assessment.lead_id,
        lead_score=10,
        priority="medium",
        status="new",
        opted_out=False,
    )
    session = MagicMock()
    session.scalar.side_effect = [lead, assessment]
    create_task = MagicMock()
    monkeypatch.setattr(rules, "create_assessment_follow_up", create_task)

    rules.apply_assessment_business_rules(session, assessment)

    assert lead.lead_score == 90
    assert lead.priority == "low"
    create_task.assert_not_called()


def test_human_approved_assessment_can_create_task_without_auto_approval(monkeypatch):
    assessment = LeadAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        status="ok",
        needs_human_review=True,
        review_status="approved",
        lead_score=75,
        priority="medium",
        recommended_action="call",
    )
    lead = SimpleNamespace(
        id=assessment.lead_id,
        lead_score=None,
        priority="low",
        status="new",
        opted_out=False,
    )
    session = MagicMock()
    session.scalar.side_effect = [lead, assessment]
    create_task = MagicMock()
    monkeypatch.setattr(rules, "create_assessment_follow_up", create_task)

    rules.apply_assessment_business_rules(session, assessment)

    create_task.assert_called_once_with(session, assessment, lead)
    assert assessment.review_status == "approved"
    assert assessment.needs_human_review is True


@pytest.mark.parametrize(
    ("lead_status", "opted_out"),
    [("won", False), ("lost", False), ("new", True)],
)
def test_closed_or_opted_out_lead_does_not_receive_automatic_task(
    monkeypatch, lead_status, opted_out
):
    assessment = LeadAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        status="ok",
        needs_human_review=False,
        review_status="not_required",
        lead_score=75,
        priority="high",
    )
    lead = SimpleNamespace(
        id=assessment.lead_id,
        lead_score=None,
        priority="medium",
        status=lead_status,
        opted_out=opted_out,
    )
    session = MagicMock()
    session.scalar.side_effect = [lead, assessment]
    create_task = MagicMock()
    monkeypatch.setattr(rules, "create_assessment_follow_up", create_task)

    rules.apply_assessment_business_rules(session, assessment)

    create_task.assert_not_called()


def test_stale_assessment_does_not_overwrite_lead_or_create_task(monkeypatch):
    assessment = LeadAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        status="ok",
        needs_human_review=False,
        review_status="not_required",
        lead_score=90,
        priority="high",
    )
    lead = SimpleNamespace(
        id=assessment.lead_id,
        lead_score=30,
        priority="low",
        status="new",
        opted_out=False,
    )
    latest = SimpleNamespace(id=uuid.uuid4())
    session = MagicMock()
    session.scalar.side_effect = [lead, latest]
    create_task = MagicMock()
    monkeypatch.setattr(rules, "create_assessment_follow_up", create_task)

    rules.apply_assessment_business_rules(session, assessment)

    assert lead.lead_score == 30
    assert lead.priority == "low"
    create_task.assert_not_called()


@pytest.mark.parametrize("status", ["fallback", "failed"])
def test_provider_failure_does_not_overwrite_lead_score_or_create_task(monkeypatch, status):
    assessment = LeadAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        conversation_id=None,
        status=status,
        needs_human_review=True,
        review_status="pending",
        lead_score=0,
        priority="low",
    )
    lead = SimpleNamespace(
        id=assessment.lead_id,
        lead_score=65,
        priority="medium",
        status="new",
        opted_out=False,
    )
    session = MagicMock()
    session.scalar.side_effect = [lead, assessment]
    create_task = MagicMock()
    monkeypatch.setattr(rules, "create_assessment_follow_up", create_task)

    rules.apply_assessment_business_rules(session, assessment)

    assert lead.lead_score == 65
    assert lead.priority == "medium"
    create_task.assert_not_called()
