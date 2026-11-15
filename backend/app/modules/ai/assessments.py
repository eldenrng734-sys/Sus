import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.modules.ai.models import LeadAssessment
from app.modules.ai.schemas import AssessmentOut, AssessmentReviewRequest
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Lead


def _visible_assessments(context: TenantContext):
    statement = select(LeadAssessment).join(
        Lead,
        and_(
            Lead.tenant_id == LeadAssessment.tenant_id,
            Lead.id == LeadAssessment.lead_id,
        ),
    )
    statement = statement.where(LeadAssessment.tenant_id == context.tenant_id)
    return apply_data_scope(statement, Lead, context)


def list_assessments(
    session: Session,
    context: TenantContext,
    *,
    needs_human_review: bool | None,
    review_status: str | None,
    limit: int,
    offset: int,
) -> list[AssessmentOut]:
    statement = _visible_assessments(context)
    if needs_human_review is not None:
        statement = statement.where(LeadAssessment.needs_human_review == needs_human_review)
    if review_status is not None:
        statement = statement.where(LeadAssessment.review_status == review_status)
    statement = (
        statement.order_by(LeadAssessment.created_at.desc(), LeadAssessment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [AssessmentOut.model_validate(item) for item in session.scalars(statement).all()]


def _assessment_by_id(
    session: Session,
    context: TenantContext,
    assessment_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> LeadAssessment:
    statement = _visible_assessments(context).where(LeadAssessment.id == assessment_id)
    if for_update:
        statement = statement.with_for_update(of=LeadAssessment)
    assessment = session.scalar(statement)
    if assessment is None:
        raise AuthError(404, "not_found", "Assessment not found")
    return assessment


def get_assessment(
    session: Session,
    context: TenantContext,
    assessment_id: uuid.UUID,
) -> AssessmentOut:
    assessment = _assessment_by_id(session, context, assessment_id)
    return AssessmentOut.model_validate(assessment)


def review_assessment(
    session: Session,
    context: TenantContext,
    assessment_id: uuid.UUID,
    body: AssessmentReviewRequest,
) -> AssessmentOut:
    assessment = _assessment_by_id(session, context, assessment_id, for_update=True)
    if not assessment.needs_human_review or assessment.review_status != "pending":
        raise AuthError(409, "conflict", "Assessment is not awaiting human review")

    assessment.review_status = body.review_status
    assessment.reviewed_by_user_id = context.user_id
    assessment.reviewed_at = datetime.now(UTC)
    assessment.review_note = body._normalize_note(body.review_note)
    session.commit()
    return AssessmentOut.model_validate(assessment)
