"""Pydantic schemas for Dashboard Summary API (API_CONTRACT.md section 11)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DashboardPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: date = Field(..., alias="from")
    to_date: date = Field(..., alias="to")
    timezone: str


class RepKPIs(BaseModel):
    new_leads: int = 0
    high_priority_leads: int = 0
    follow_ups_due_today: int = 0
    overdue_tasks: int = 0
    conversion_rate: float = 0.0


class TeamKPIs(BaseModel):
    new_leads: int = 0
    high_priority_leads: int = 0
    follow_ups_due_today: int = 0
    overdue_tasks: int = 0
    conversion_rate: float = 0.0
    avg_first_response_seconds: int | None = None
    follow_up_completion_rate: float | None = None


class CompanyKPIs(BaseModel):
    new_leads: int = 0
    won_leads: int = 0
    high_priority_leads: int = 0
    conversion_rate: float = 0.0


class SourceCount(BaseModel):
    source: str
    count: int


class StatusCount(BaseModel):
    status: str
    count: int


class LostReasonCount(BaseModel):
    reason: str
    count: int


class PipelineCounts(BaseModel):
    new: int = 0
    contacted: int = 0
    qualified: int = 0
    proposal: int = 0
    won: int = 0
    lost: int = 0


class RepPerformance(BaseModel):
    user_id: uuid.UUID
    name: str
    leads: int = 0
    won: int = 0
    conversion_rate: float = 0.0


class RecentConversation(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str
    channel: str
    status: str
    last_message_at: datetime | None = None


class IntegrationHealthItem(BaseModel):
    provider: str
    status: str
    last_event_at: datetime | None = None


class AutomationHealthSummary(BaseModel):
    workflow_a_success_rate: float = 1.0
    workflow_b_success_rate: float = 1.0
    failed_runs_24h: int = 0


class DashboardMeResponse(BaseModel):
    scope: Literal["me"] = "me"
    period: DashboardPeriod
    kpis: RepKPIs
    pipeline: PipelineCounts
    recent_conversations: list[RecentConversation] = Field(default_factory=list)


class DashboardTeamResponse(BaseModel):
    scope: Literal["team"] = "team"
    period: DashboardPeriod
    kpis: TeamKPIs
    leads_by_source: list[SourceCount] = Field(default_factory=list)
    leads_by_status: list[StatusCount] = Field(default_factory=list)
    pipeline: PipelineCounts
    lost_reasons: list[LostReasonCount] = Field(default_factory=list)
    reps: list[RepPerformance] = Field(default_factory=list)


class DashboardCompanyResponse(BaseModel):
    scope: Literal["company"] = "company"
    period: DashboardPeriod
    kpis: CompanyKPIs
    leads_by_source: list[SourceCount] = Field(default_factory=list)
    leads_by_status: list[StatusCount] = Field(default_factory=list)
    pipeline: PipelineCounts
    lost_reasons: list[LostReasonCount] = Field(default_factory=list)
    reps: list[RepPerformance] = Field(default_factory=list)
    users_by_role: dict[str, int] = Field(default_factory=dict)
    integration_health: list[IntegrationHealthItem] = Field(default_factory=list)
    automation_health: AutomationHealthSummary | None = None


DashboardSummaryData = DashboardMeResponse | DashboardTeamResponse | DashboardCompanyResponse


class DashboardSummaryEnvelope(BaseModel):
    data: DashboardSummaryData
