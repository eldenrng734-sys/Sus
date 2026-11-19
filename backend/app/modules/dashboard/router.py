"""Dashboard summary endpoint router (API_CONTRACT.md section 11)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.dashboard import service
from app.modules.dashboard.schemas import (
    DashboardSummaryEnvelope,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryEnvelope)
def get_summary(
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    scope: str = Query(default="me", description="Dashboard scope: 'me', 'team', or 'company'"),
    from_date: date | None = Query(
        default=None, alias="from", description="ISO start date (YYYY-MM-DD)"
    ),
    to_date: date | None = Query(default=None, alias="to", description="ISO end date (YYYY-MM-DD)"),
    team_id: uuid.UUID | None = Query(default=None, description="Optional team filter"),
) -> DashboardSummaryEnvelope:
    """Get aggregated dashboard metrics scoped to rep, team, or company."""
    summary_data = service.get_dashboard_summary(
        session,
        context,
        scope=scope,
        from_date=from_date,
        to_date=to_date,
        team_id=team_id,
    )
    return DashboardSummaryEnvelope(data=summary_data)
