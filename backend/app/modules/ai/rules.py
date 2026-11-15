import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai.models import LeadAssessment
from app.modules.leads.models import Lead
from app.modules.tasks.service import create_assessment_follow_up


class AssessmentSignals(Protocol):
    category: str | None
    intent: str | None
    buying_stage: str | None
    sentiment: str | None
    confidence: float | None


INTENT_POINTS = {
    "request_demo": 35,
    "pricing": 30,
    "support": 20,
    "info": 15,
    "other": 10,
    "complaint": 0,
    "unknown": 0,
}
BUYING_STAGE_POINTS = {"decision": 20, "consideration": 14, "awareness": 7}
CATEGORY_POINTS = {"business_customer": 15, "partner": 10, "individual": 8}
SENTIMENT_POINTS = {"positive": 15, "neutral": 8, "negative": 0}
HIGH_RISK_CATEGORIES = {"spam", "unknown"}
HIGH_RISK_INTENTS = {"complaint", "unknown"}


def calculate_lead_score(assessment: AssessmentSignals) -> int:
    """Return a reproducible 0-100 score; never use the model-provided score."""
    if not any((assessment.category, assessment.intent, assessment.buying_stage)):
        raise ValueError("assessment lacks lead-scoring signals")
    confidence = assessment.confidence
    confidence_points = (
        15
        if confidence is not None and confidence >= 0.9
        else 12
        if confidence is not None and confidence >= 0.75
        else 8
        if confidence is not None and confidence >= 0.6
        else 4
        if confidence is not None and confidence >= 0.4
        else 0
    )
    score = (
        INTENT_POINTS.get(assessment.intent, 0)
        + BUYING_STAGE_POINTS.get(assessment.buying_stage, 0)
        + CATEGORY_POINTS.get(assessment.category, 0)
        + SENTIMENT_POINTS.get(assessment.sentiment, 0)
        + confidence_points
    )
    return max(0, min(100, score))


def has_lead_scoring_signals(assessment: AssessmentSignals) -> bool:
    return any((assessment.category, assessment.intent, assessment.buying_stage))


def requires_human_review(assessment: AssessmentSignals, status: str) -> bool:
    """Require review for uncertain/provider-failure results and risky classifications."""
    return (
        status != "ok"
        or assessment.confidence is None
        or assessment.confidence < 0.6
        or assessment.category in HIGH_RISK_CATEGORIES
        or assessment.intent in HIGH_RISK_INTENTS
        or assessment.sentiment == "negative"
    )


def determine_priority(
    assessment: AssessmentSignals,
    score: int,
    review_required: bool,
) -> str:
    """Map the deterministic score to priority, capping risk/review cases."""
    if (
        assessment.category in HIGH_RISK_CATEGORIES
        or assessment.intent in HIGH_RISK_INTENTS
        or assessment.sentiment == "negative"
    ):
        return "low"
    if review_required:
        return "medium" if score >= 40 else "low"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def lock_lead_for_assessment(
    session: Session,
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> Lead:
    """Serialize assessment writes for a lead and keep the lock in the caller's transaction."""
    lead = session.scalar(
        select(Lead)
        .where(
            Lead.tenant_id == tenant_id,
            Lead.id == lead_id,
        )
        .with_for_update()
    )
    if lead is None:
        raise RuntimeError("Cannot apply assessment rules without its tenant lead")
    return lead


def apply_assessment_business_rules(
    session: Session,
    assessment: LeadAssessment,
    lead: Lead | None = None,
) -> None:
    """Project the newest tenant-scoped result and enqueue safe follow-up work."""
    if lead is None:
        lead = lock_lead_for_assessment(session, assessment.tenant_id, assessment.lead_id)
    latest = session.scalar(
        select(LeadAssessment)
        .where(
            LeadAssessment.tenant_id == assessment.tenant_id,
            LeadAssessment.lead_id == assessment.lead_id,
        )
        .order_by(LeadAssessment.created_at.desc(), LeadAssessment.id.desc())
        .limit(1)
    )
    if latest is None or latest.id != assessment.id:
        return

    if assessment.status != "ok":
        return

    if assessment.lead_score is not None and assessment.priority is not None:
        lead.lead_score = assessment.lead_score
        lead.priority = assessment.priority
    else:
        return

    if (
        assessment.review_status not in {"not_required", "approved"}
        or lead.status in {"won", "lost"}
        or lead.opted_out
    ):
        return

    create_assessment_follow_up(session, assessment, lead)
