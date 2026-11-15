import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member, require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.ai import assessments
from app.modules.ai.schemas import AssessmentReviewRequest

router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])


@router.get("")
def list_assessments(
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    needs_human_review: bool | None = None,
    review_status: Literal["not_required", "pending", "approved", "rejected"] | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    data = assessments.list_assessments(
        session,
        context,
        needs_human_review=needs_human_review,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    return {"data": data, "meta": {"limit": limit, "offset": offset}}


@router.get("/{assessment_id}")
def get_assessment(
    assessment_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": assessments.get_assessment(session, context, assessment_id)}


@router.patch("/{assessment_id}/review")
def review_assessment(
    assessment_id: uuid.UUID,
    body: AssessmentReviewRequest,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": assessments.review_assessment(session, context, assessment_id, body)}
