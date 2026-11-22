"""Dashboard service implementing scope-based aggregation queries.

Security & RLS Guarantee:
Every query enforces tenant isolation via TenantContext and applies explicit SQL
WHERE filters based on the caller's role and target scope before executing.
Cross-role data is NEVER loaded into Python memory.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.outbox_models import OutboxEvent
from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation
from app.modules.dashboard.schemas import (
    AutomationHealthSummary,
    CompanyKPIs,
    DashboardCompanyResponse,
    DashboardMeResponse,
    DashboardPeriod,
    DashboardTeamResponse,
    IntegrationHealthItem,
    LostReasonCount,
    PipelineCounts,
    RecentConversation,
    RepKPIs,
    RepPerformance,
    SourceCount,
    StatusCount,
    TeamKPIs,
)
from app.modules.integrations.models import Integration
from app.modules.leads.models import Lead
from app.modules.settings.models import TenantSettings
from app.modules.tasks.models import Task
from app.modules.tenants.models import Team, TenantMembership
from app.modules.users.models import User

logger = logging.getLogger("app.dashboard")


def get_dashboard_summary(
    session: Session,
    context: TenantContext,
    *,
    scope: str,
    from_date: date | None = None,
    to_date: date | None = None,
    team_id: uuid.UUID | None = None,
) -> DashboardMeResponse | DashboardTeamResponse | DashboardCompanyResponse:
    """Validate authorization, parse period, and execute scope-appropriate queries."""
    # 1. Authorization check before any query runs
    _validate_scope_authorization(context, scope, team_id)

    # 2. Timezone & date range resolution
    tz_str = _resolve_tenant_timezone(session, context.tenant_id)
    try:
        tz = ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("Asia/Dhaka")
        tz_str = "Asia/Dhaka"

    period, range_start, range_end, today_start, today_end = _resolve_period_dates(
        tz, tz_str, from_date, to_date
    )

    # 3. Route to scope-specific query builder
    if scope == "me":
        return _build_me_dashboard(
            session, context, period, range_start, range_end, today_start, today_end
        )
    elif scope == "team":
        # Resolve target team
        target_team = team_id if context.role == "admin" and team_id else context.team_id
        if target_team is None and context.role == "admin":
            target_team = session.scalar(
                select(Team.id).where(Team.tenant_id == context.tenant_id).order_by(Team.created_at).limit(1)
            )
        return _build_team_dashboard(
            session, context, target_team, period, range_start, range_end, today_start, today_end
        )
    elif scope == "company":
        return _build_company_dashboard(
            session, context, team_id, period, range_start, range_end, today_start, today_end
        )
    else:
        raise HTTPException(
            status_code=422,
            detail=[{"field": "scope", "code": "invalid", "message": f"Invalid scope: {scope}"}],
        )


def _validate_scope_authorization(
    context: TenantContext,
    scope: str,
    requested_team_id: uuid.UUID | None,
) -> None:
    """Enforce role permissions strictly BEFORE running any database query."""
    if scope == "me":
        # Any authenticated tenant member can see their own scope
        return

    if scope == "team":
        if context.role not in ("manager", "admin"):
            raise AuthError(403, "forbidden", "You do not have permission for team scope")
        if context.role == "manager":
            # Manager can only query their own team
            if requested_team_id is not None and requested_team_id != context.team_id:
                raise AuthError(403, "forbidden", "Managers can only access their own team")
        return

    if scope == "company":
        if context.role != "admin":
            raise AuthError(403, "forbidden", "You do not have permission for company scope")
        return

    raise HTTPException(
        status_code=422,
        detail=[{"field": "scope", "code": "invalid", "message": f"Invalid scope: {scope}"}],
    )


def _resolve_tenant_timezone(session: Session, tenant_id: uuid.UUID) -> str:
    settings = session.get(TenantSettings, tenant_id)
    if settings and settings.timezone:
        return settings.timezone
    return "Asia/Dhaka"


def _resolve_period_dates(
    tz: ZoneInfo,
    tz_str: str,
    from_date: date | None,
    to_date: date | None,
) -> tuple[DashboardPeriod, datetime, datetime, datetime, datetime]:
    now_tz = datetime.now(tz)
    today = now_tz.date()

    resolved_to = to_date if to_date is not None else today
    resolved_from = from_date if from_date is not None else (resolved_to - timedelta(days=30))

    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "field": "from",
                    "code": "invalid",
                    "message": "'from' date must be on or before 'to' date",
                }
            ],
        )

    delta_days = (resolved_to - resolved_from).days
    if delta_days > 366:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "field": "from",
                    "code": "invalid",
                    "message": f"Date range exceeds 366 days ({delta_days} days)",
                }
            ],
        )

    # Convert date boundaries to UTC timestamps
    range_start = datetime.combine(resolved_from, time.min, tzinfo=tz).astimezone(timezone.utc)
    range_end = datetime.combine(resolved_to, time.max, tzinfo=tz).astimezone(timezone.utc)

    today_start = datetime.combine(today, time.min, tzinfo=tz).astimezone(timezone.utc)
    today_end = datetime.combine(today, time.max, tzinfo=tz).astimezone(timezone.utc)

    period = DashboardPeriod(
        from_date=resolved_from,
        to_date=resolved_to,
        timezone=tz_str,
    )
    return period, range_start, range_end, today_start, today_end


# -----------------------------------------------------------------------------
# Scope: me (Sales Rep)
# -----------------------------------------------------------------------------


def _build_me_dashboard(
    session: Session,
    context: TenantContext,
    period: DashboardPeriod,
    range_start: datetime,
    range_end: datetime,
    today_start: datetime,
    today_end: datetime,
) -> DashboardMeResponse:
    tenant_id = context.tenant_id
    user_id = context.user_id

    # Filter for rep's leads
    rep_leads_filter = [Lead.assigned_user_id == user_id]

    # Pipeline & Status counts
    pipeline, _ = _query_pipeline_and_status(
        session, tenant_id, rep_leads_filter, range_start, range_end
    )

    # Rep KPIs
    new_leads_count = (
        session.scalar(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.assigned_user_id == user_id,
                Lead.created_at >= range_start,
                Lead.created_at <= range_end,
            )
        )
        or 0
    )

    high_priority_count = (
        session.scalar(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.assigned_user_id == user_id,
                Lead.priority == "high",
                Lead.status.notin_(["won", "lost"]),
            )
        )
        or 0
    )

    follow_ups_due_today = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.assigned_user_id == user_id,
                Task.status == "open",
                Task.type == "follow_up",
                Task.due_at >= today_start,
                Task.due_at <= today_end,
            )
        )
        or 0
    )

    overdue_tasks_count = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.assigned_user_id == user_id,
                Task.status == "open",
                Task.due_at < today_start,
            )
        )
        or 0
    )

    total_leads_in_period = new_leads_count
    won_leads_in_period = pipeline.won
    conversion_rate = (
        round(won_leads_in_period / total_leads_in_period, 2) if total_leads_in_period > 0 else 0.0
    )

    kpis = RepKPIs(
        new_leads=new_leads_count,
        high_priority_leads=high_priority_count,
        follow_ups_due_today=follow_ups_due_today,
        overdue_tasks=overdue_tasks_count,
        conversion_rate=conversion_rate,
    )

    # Recent conversations
    recent_convs = _query_recent_conversations(session, tenant_id, user_id)

    return DashboardMeResponse(
        scope="me",
        period=period,
        kpis=kpis,
        pipeline=pipeline,
        recent_conversations=recent_convs,
    )


# -----------------------------------------------------------------------------
# Scope: team (Sales Manager)
# -----------------------------------------------------------------------------


def _build_team_dashboard(
    session: Session,
    context: TenantContext,
    team_id: uuid.UUID | None,
    period: DashboardPeriod,
    range_start: datetime,
    range_end: datetime,
    today_start: datetime,
    today_end: datetime,
) -> DashboardTeamResponse:
    tenant_id = context.tenant_id

    # If team_id is None, manager has no assigned team -> empty metrics
    if team_id is None:
        return DashboardTeamResponse(
            scope="team",
            period=period,
            kpis=TeamKPIs(),
            pipeline=PipelineCounts(),
        )

    team_leads_filter = [Lead.team_id == team_id]

    pipeline, leads_by_status = _query_pipeline_and_status(
        session, tenant_id, team_leads_filter, range_start, range_end
    )
    leads_by_source = _query_leads_by_source(
        session, tenant_id, team_leads_filter, range_start, range_end
    )
    lost_reasons = _query_lost_reasons(
        session, tenant_id, team_leads_filter, range_start, range_end
    )

    # Team KPIs
    new_leads_count = (
        session.scalar(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.team_id == team_id,
                Lead.created_at >= range_start,
                Lead.created_at <= range_end,
            )
        )
        or 0
    )

    high_priority_count = (
        session.scalar(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.team_id == team_id,
                Lead.priority == "high",
                Lead.status.notin_(["won", "lost"]),
            )
        )
        or 0
    )

    follow_ups_due_today = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.team_id == team_id,
                Task.status == "open",
                Task.type == "follow_up",
                Task.due_at >= today_start,
                Task.due_at <= today_end,
            )
        )
        or 0
    )

    overdue_tasks_count = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.team_id == team_id,
                Task.status == "open",
                Task.due_at < today_start,
            )
        )
        or 0
    )

    conversion_rate = round(pipeline.won / new_leads_count, 2) if new_leads_count > 0 else 0.0

    # Cut-first: follow-up completion rate
    total_team_follow_ups = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.team_id == team_id,
                Task.type == "follow_up",
                Task.due_at >= range_start,
                Task.due_at <= range_end,
            )
        )
        or 0
    )
    completed_team_follow_ups = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.team_id == team_id,
                Task.type == "follow_up",
                Task.status == "done",
                Task.due_at >= range_start,
                Task.due_at <= range_end,
            )
        )
        or 0
    )
    completion_rate = (
        round(completed_team_follow_ups / total_team_follow_ups, 2)
        if total_team_follow_ups > 0
        else None
    )

    kpis = TeamKPIs(
        new_leads=new_leads_count,
        high_priority_leads=high_priority_count,
        follow_ups_due_today=follow_ups_due_today,
        overdue_tasks=overdue_tasks_count,
        conversion_rate=conversion_rate,
        avg_first_response_seconds=None,  # Cut-first optional metric
        follow_up_completion_rate=completion_rate,
    )

    reps = _query_reps_performance(session, tenant_id, team_id, range_start, range_end)

    return DashboardTeamResponse(
        scope="team",
        period=period,
        kpis=kpis,
        leads_by_source=leads_by_source,
        leads_by_status=leads_by_status,
        pipeline=pipeline,
        lost_reasons=lost_reasons,
        reps=reps,
    )


# -----------------------------------------------------------------------------
# Scope: company (Company Admin)
# -----------------------------------------------------------------------------


def _build_company_dashboard(
    session: Session,
    context: TenantContext,
    team_id: uuid.UUID | None,
    period: DashboardPeriod,
    range_start: datetime,
    range_end: datetime,
    today_start: datetime,
    today_end: datetime,
) -> DashboardCompanyResponse:
    tenant_id = context.tenant_id

    company_leads_filter = [Lead.team_id == team_id] if team_id else []

    pipeline, leads_by_status = _query_pipeline_and_status(
        session, tenant_id, company_leads_filter, range_start, range_end
    )
    leads_by_source = _query_leads_by_source(
        session, tenant_id, company_leads_filter, range_start, range_end
    )
    lost_reasons = _query_lost_reasons(
        session, tenant_id, company_leads_filter, range_start, range_end
    )

    new_leads_count = (
        session.scalar(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.created_at >= range_start,
                Lead.created_at <= range_end,
                *company_leads_filter,
            )
        )
        or 0
    )

    high_priority_count = (
        session.scalar(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.priority == "high",
                Lead.status.notin_(["won", "lost"]),
                *company_leads_filter,
            )
        )
        or 0
    )

    conversion_rate = round(pipeline.won / new_leads_count, 2) if new_leads_count > 0 else 0.0

    kpis = CompanyKPIs(
        new_leads=new_leads_count,
        won_leads=pipeline.won,
        high_priority_leads=high_priority_count,
        conversion_rate=conversion_rate,
    )

    reps = _query_reps_performance(session, tenant_id, team_id, range_start, range_end)
    users_by_role = _query_users_by_role(session, tenant_id)
    integration_health = _query_integration_health(session, tenant_id)
    automation_health = _query_automation_health(session, tenant_id)

    return DashboardCompanyResponse(
        scope="company",
        period=period,
        kpis=kpis,
        leads_by_source=leads_by_source,
        leads_by_status=leads_by_status,
        pipeline=pipeline,
        lost_reasons=lost_reasons,
        reps=reps,
        users_by_role=users_by_role,
        integration_health=integration_health,
        automation_health=automation_health,
    )


# -----------------------------------------------------------------------------
# Common Query Helpers (RLS-guaranteed via tenant_id)
# -----------------------------------------------------------------------------


def _query_pipeline_and_status(
    session: Session,
    tenant_id: uuid.UUID,
    extra_filter: list,
    range_start: datetime,
    range_end: datetime,
) -> tuple[PipelineCounts, list[StatusCount]]:
    stmt = (
        select(Lead.status, func.count(Lead.id))
        .where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= range_start,
            Lead.created_at <= range_end,
            *extra_filter,
        )
        .group_by(Lead.status)
    )
    rows = session.execute(stmt).all()
    counts: dict[str, int] = {status: count for status, count in rows}

    pipeline = PipelineCounts(
        new=counts.get("new", 0),
        contacted=counts.get("contacted", 0),
        qualified=counts.get("qualified", 0),
        proposal=counts.get("proposal", 0),
        won=counts.get("won", 0),
        lost=counts.get("lost", 0),
    )

    status_list = [StatusCount(status=status, count=count) for status, count in rows]
    return pipeline, status_list


def _query_leads_by_source(
    session: Session,
    tenant_id: uuid.UUID,
    extra_filter: list,
    range_start: datetime,
    range_end: datetime,
) -> list[SourceCount]:
    stmt = (
        select(Lead.source, func.count(Lead.id))
        .where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= range_start,
            Lead.created_at <= range_end,
            *extra_filter,
        )
        .group_by(Lead.source)
        .order_by(func.count(Lead.id).desc())
    )
    rows = session.execute(stmt).all()
    return [SourceCount(source=source, count=count) for source, count in rows]


def _query_lost_reasons(
    session: Session,
    tenant_id: uuid.UUID,
    extra_filter: list,
    range_start: datetime,
    range_end: datetime,
) -> list[LostReasonCount]:
    stmt = (
        select(Lead.lost_reason, func.count(Lead.id))
        .where(
            Lead.tenant_id == tenant_id,
            Lead.status == "lost",
            Lead.lost_reason.isnot(None),
            Lead.created_at >= range_start,
            Lead.created_at <= range_end,
            *extra_filter,
        )
        .group_by(Lead.lost_reason)
        .order_by(func.count(Lead.id).desc())
    )
    rows = session.execute(stmt).all()
    return [LostReasonCount(reason=reason, count=count) for reason, count in rows]


def _query_recent_conversations(
    session: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[RecentConversation]:
    stmt = (
        select(
            Conversation.id,
            Conversation.lead_id,
            Lead.name,
            Conversation.channel,
            Conversation.status,
            Conversation.last_message_at,
        )
        .join(
            Lead,
            (Lead.tenant_id == Conversation.tenant_id) & (Lead.id == Conversation.lead_id),
        )
        .where(
            Conversation.tenant_id == tenant_id,
            (Conversation.assigned_user_id == user_id) | (Lead.assigned_user_id == user_id),
        )
        .order_by(Conversation.last_message_at.desc().nullslast())
        .limit(5)
    )
    rows = session.execute(stmt).all()
    return [
        RecentConversation(
            id=row[0],
            lead_id=row[1],
            lead_name=row[2],
            channel=row[3],
            status=row[4],
            last_message_at=row[5],
        )
        for row in rows
    ]


def _query_reps_performance(
    session: Session,
    tenant_id: uuid.UUID,
    team_id: uuid.UUID | None,
    range_start: datetime,
    range_end: datetime,
) -> list[RepPerformance]:
    # Active reps for the tenant
    membership_filters = [
        TenantMembership.tenant_id == tenant_id,
        TenantMembership.role == "rep",
    ]
    if team_id is not None:
        membership_filters.append(TenantMembership.team_id == team_id)

    reps_stmt = (
        select(
            User.id,
            func.coalesce(User.full_name, User.email).label("name"),
            func.count(Lead.id).label("leads_count"),
            func.count(case((Lead.status == "won", 1))).label("won_count"),
        )
        .select_from(TenantMembership)
        .join(User, User.id == TenantMembership.user_id)
        .outerjoin(
            Lead,
            (Lead.tenant_id == TenantMembership.tenant_id)
            & (Lead.assigned_user_id == TenantMembership.user_id)
            & (Lead.created_at >= range_start)
            & (Lead.created_at <= range_end),
        )
        .where(*membership_filters)
        .group_by(User.id, User.full_name, User.email)
        .order_by(func.count(Lead.id).desc())
    )
    rows = session.execute(reps_stmt).all()

    result = []
    for uid, name, leads_cnt, won_cnt in rows:
        conv_rate = round(won_cnt / leads_cnt, 2) if leads_cnt > 0 else 0.0
        result.append(
            RepPerformance(
                user_id=uid,
                name=name,
                leads=leads_cnt,
                won=won_cnt,
                conversion_rate=conv_rate,
            )
        )
    return result


def _query_users_by_role(
    session: Session,
    tenant_id: uuid.UUID,
) -> dict[str, int]:
    stmt = (
        select(TenantMembership.role, func.count(TenantMembership.user_id))
        .where(TenantMembership.tenant_id == tenant_id)
        .group_by(TenantMembership.role)
    )
    rows = session.execute(stmt).all()
    return {role: count for role, count in rows}


def _query_integration_health(
    session: Session,
    tenant_id: uuid.UUID,
) -> list[IntegrationHealthItem]:
    stmt = (
        select(
            Integration.provider,
            Integration.status,
            Integration.updated_at,
        )
        .where(Integration.tenant_id == tenant_id)
        .order_by(Integration.provider)
    )
    rows = session.execute(stmt).all()
    return [
        IntegrationHealthItem(provider=provider, status=status, last_event_at=updated_at)
        for provider, status, updated_at in rows
    ]


def _query_automation_health(
    session: Session,
    tenant_id: uuid.UUID,
) -> AutomationHealthSummary:
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    # Failed runs in last 24h
    failed_24h = (
        session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.status == "dead",
                OutboxEvent.created_at >= twenty_four_hours_ago,
            )
        )
        or 0
    )

    # Workflow A (lead.created) success rate in last 7 days
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    wf_a_processed = (
        session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "lead.created",
                OutboxEvent.status == "processed",
                OutboxEvent.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    wf_a_dead = (
        session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "lead.created",
                OutboxEvent.status == "dead",
                OutboxEvent.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    wf_a_total = wf_a_processed + wf_a_dead
    wf_a_rate = round(wf_a_processed / wf_a_total, 2) if wf_a_total > 0 else 1.0

    # Workflow B (task.due) success rate
    wf_b_processed = (
        session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "task.due",
                OutboxEvent.status == "processed",
                OutboxEvent.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    wf_b_dead = (
        session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "task.due",
                OutboxEvent.status == "dead",
                OutboxEvent.created_at >= seven_days_ago,
            )
        )
        or 0
    )
    wf_b_total = wf_b_processed + wf_b_dead
    wf_b_rate = round(wf_b_processed / wf_b_total, 2) if wf_b_total > 0 else 1.0

    return AutomationHealthSummary(
        workflow_a_success_rate=wf_a_rate,
        workflow_b_success_rate=wf_b_rate,
        failed_runs_24h=failed_24h,
    )
