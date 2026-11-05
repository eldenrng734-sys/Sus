import pytest
from pydantic import ValidationError

from app.modules.ai.schemas import AIAssessmentOutput

VALID = {
    "category": "business_customer",
    "intent": "request_demo",
    "interest": "CRM software",
    "buying_stage": "consideration",
    "sentiment": "positive",
    "priority": "high",
    "lead_score": 90,
    "recommended_action": "schedule_demo",
    "follow_up_days": 0,
    "confidence": 0.94,
}


def test_valid_output_is_accepted():
    result = AIAssessmentOutput(**VALID)
    assert result.lead_score == 90
    assert result.intent == "request_demo"


def test_score_above_100_is_rejected():
    bad = {**VALID, "lead_score": 150}
    with pytest.raises(ValidationError):
        AIAssessmentOutput(**bad)


def test_unknown_intent_is_rejected():
    bad = {**VALID, "intent": "make_me_rich"}
    with pytest.raises(ValidationError):
        AIAssessmentOutput(**bad)


def test_missing_field_is_rejected():
    bad = {k: v for k, v in VALID.items() if k != "confidence"}
    with pytest.raises(ValidationError):
        AIAssessmentOutput(**bad)