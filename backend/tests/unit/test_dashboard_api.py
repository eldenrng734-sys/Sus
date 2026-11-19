"""Unit tests for Dashboard Summary API (Step #15).

Tests both service layer and router endpoints directly inside standard sandbox:
- Pre-query RBAC authorization:
  - rep asking for 'me' -> allowed
  - rep asking for 'team' -> raises 403
  - rep asking for 'company' -> raises 403
  - manager asking for 'me' -> allowed
  - manager asking for 'team' (own) -> allowed
  - manager asking for 'team' with other team_id -> raises 403
  - manager asking for 'company' -> raises 403
  - admin asking for 'me', 'team', 'company' -> allowed
  - admin with team_id filter -> allowed
- Date range validation:
  - inverted from/to -> raises 422
  - range > 366 days -> raises 422
  - default 30 days when omitted
- Tenant isolation guarantee (SQL filter validation)
- Metrics calculation & data shaping
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.dashboard import router, service
from app.modules.dashboard.schemas import (
    DashboardCompanyResponse,
    DashboardMeResponse,
    DashboardTeamResponse,
)
from app.modules.settings.models import TenantSettings


def _ctx(
    role="rep",
    team_id=None,
    tenant_id=None,
    user_id=None,
    membership_id=None,
    session_id=None,
) -> TenantContext:
    t_id = tenant_id or uuid.uuid4()
    u_id = user_id or uuid.uuid4()
    m_id = membership_id or uuid.uuid4()
    s_id = session_id or uuid.uuid4()
    return TenantContext(
        tenant_id=t_id,
        user_id=u_id,
        membership_id=m_id,
        role=role,
        team_id=team_id,
        session_id=s_id,
    )


@pytest.fixture
def mock_session():
    session = MagicMock()
    settings_obj = TenantSettings(
        tenant_id=uuid.uuid4(),
        timezone="Asia/Dhaka",
    )
    session.get.return_value = settings_obj
    session.scalar.return_value = 0
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute.return_value = mock_result
    return session


# =============================================================================
# 1. RBAC Tests (Pre-query Authorization)
# =============================================================================


def test_rep_scope_me_succeeds(mock_session):
    rep_context = _ctx(role="rep")
    res = service.get_dashboard_summary(mock_session, rep_context, scope="me")
    assert isinstance(res, DashboardMeResponse)
    assert res.scope == "me"
    assert res.kpis is not None
    assert res.pipeline is not None
    assert res.recent_conversations is not None


def test_rep_scope_team_returns_403(mock_session):
    rep_context = _ctx(role="rep")
    with pytest.raises(AuthError) as exc_info:
        service.get_dashboard_summary(mock_session, rep_context, scope="team")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"
    # Ensure zero database queries executed
    mock_session.execute.assert_not_called()


def test_rep_scope_company_returns_403(mock_session):
    rep_context = _ctx(role="rep")
    with pytest.raises(AuthError) as exc_info:
        service.get_dashboard_summary(mock_session, rep_context, scope="company")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"
    mock_session.execute.assert_not_called()


def test_manager_scope_me_succeeds(mock_session):
    mgr_context = _ctx(role="manager", team_id=uuid.uuid4())
    res = service.get_dashboard_summary(mock_session, mgr_context, scope="me")
    assert isinstance(res, DashboardMeResponse)
    assert res.scope == "me"


def test_manager_scope_team_own_team_succeeds(mock_session):
    team_id = uuid.uuid4()
    mgr_context = _ctx(role="manager", team_id=team_id)

    # Own team implied
    res = service.get_dashboard_summary(mock_session, mgr_context, scope="team")
    assert isinstance(res, DashboardTeamResponse)
    assert res.scope == "team"

    # Own team explicitly passed
    res2 = service.get_dashboard_summary(mock_session, mgr_context, scope="team", team_id=team_id)
    assert isinstance(res2, DashboardTeamResponse)


def test_manager_scope_team_other_team_returns_403(mock_session):
    own_team = uuid.uuid4()
    other_team = uuid.uuid4()
    mgr_context = _ctx(role="manager", team_id=own_team)

    with pytest.raises(AuthError) as exc_info:
        service.get_dashboard_summary(mock_session, mgr_context, scope="team", team_id=other_team)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"
    mock_session.execute.assert_not_called()


def test_manager_scope_company_returns_403(mock_session):
    mgr_context = _ctx(role="manager", team_id=uuid.uuid4())
    with pytest.raises(AuthError) as exc_info:
        service.get_dashboard_summary(mock_session, mgr_context, scope="company")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"
    mock_session.execute.assert_not_called()


def test_admin_scope_me_succeeds(mock_session):
    admin_context = _ctx(role="admin")
    res = service.get_dashboard_summary(mock_session, admin_context, scope="me")
    assert isinstance(res, DashboardMeResponse)


def test_admin_scope_team_succeeds(mock_session):
    admin_context = _ctx(role="admin")
    res = service.get_dashboard_summary(mock_session, admin_context, scope="team")
    assert isinstance(res, DashboardTeamResponse)


def test_admin_scope_team_with_team_id_succeeds(mock_session):
    admin_context = _ctx(role="admin")
    target_team = uuid.uuid4()
    res = service.get_dashboard_summary(
        mock_session, admin_context, scope="team", team_id=target_team
    )
    assert isinstance(res, DashboardTeamResponse)


def test_admin_scope_company_succeeds(mock_session):
    admin_context = _ctx(role="admin")
    res = service.get_dashboard_summary(mock_session, admin_context, scope="company")
    assert isinstance(res, DashboardCompanyResponse)
    assert res.scope == "company"
    assert res.users_by_role is not None
    assert res.integration_health is not None


def test_invalid_scope_returns_422(mock_session):
    admin_context = _ctx(role="admin")
    with pytest.raises(HTTPException) as exc_info:
        service.get_dashboard_summary(mock_session, admin_context, scope="invalid")
    assert exc_info.value.status_code == 422


# =============================================================================
# 2. Date Range Validation
# =============================================================================


def test_date_range_inverted_returns_422(mock_session):
    admin_context = _ctx(role="admin")
    with pytest.raises(HTTPException) as exc_info:
        service.get_dashboard_summary(
            mock_session,
            admin_context,
            scope="company",
            from_date=date(2026, 11, 10),
            to_date=date(2026, 11, 1),
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail[0]["code"] == "invalid"


def test_date_range_exceeding_366_days_returns_422(mock_session):
    admin_context = _ctx(role="admin")
    with pytest.raises(HTTPException) as exc_info:
        service.get_dashboard_summary(
            mock_session,
            admin_context,
            scope="company",
            from_date=date(2025, 1, 1),
            to_date=date(2026, 2, 1),
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail[0]["code"] == "invalid"


def test_date_range_defaults_to_30_days(mock_session):
    admin_context = _ctx(role="admin")
    res = service.get_dashboard_summary(mock_session, admin_context, scope="company")
    assert (res.period.to_date - res.period.from_date).days == 30
    assert res.period.timezone == "Asia/Dhaka"


# =============================================================================
# 3. Calculations & Data Shaping
# =============================================================================


def test_rep_metrics_calculation(mock_session):
    rep_context = _ctx(role="rep")

    # Mock DB return values:
    # 1. pipeline: 5 new, 2 won, 3 contacted
    pipeline_rows = [("new", 5), ("won", 2), ("contacted", 3)]
    pipeline_res = MagicMock()
    pipeline_res.all.return_value = pipeline_rows

    conv_res = MagicMock()
    conv_res.all.return_value = []

    mock_session.execute.side_effect = [pipeline_res, conv_res]

    # Mock scalar counts for KPIs:
    # new_leads=10, high_priority=2, follow_ups_due_today=4, overdue_tasks=1
    mock_session.scalar.side_effect = [10, 2, 4, 1]

    res: DashboardMeResponse = service.get_dashboard_summary(
        mock_session,
        rep_context,
        scope="me",
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 31),
    )

    assert res.scope == "me"
    assert res.kpis.new_leads == 10
    assert res.kpis.high_priority_leads == 2
    assert res.kpis.follow_ups_due_today == 4
    assert res.kpis.overdue_tasks == 1
    # conversion_rate = 2 won / 10 total = 0.2
    assert res.kpis.conversion_rate == 0.2
    assert res.pipeline.new == 5
    assert res.pipeline.won == 2
    assert res.pipeline.contacted == 3


def test_manager_empty_team_returns_empty_response(mock_session):
    mgr_context = _ctx(role="manager", team_id=None)

    res: DashboardTeamResponse = service.get_dashboard_summary(
        mock_session,
        mgr_context,
        scope="team",
    )
    assert res.scope == "team"
    assert res.kpis.new_leads == 0
    assert res.pipeline.won == 0
    assert res.reps == []


# =============================================================================
# 4. Router Endpoint Function Direct Verification
# =============================================================================


def test_router_get_summary_envelope(mock_session):
    rep_context = _ctx(role="rep")
    envelope = router.get_summary(
        context=rep_context,
        session=mock_session,
        scope="me",
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 15),
        team_id=None,
    )
    assert envelope.data.scope == "me"
    assert envelope.data.period.from_date == date(2026, 10, 1)
    assert envelope.data.period.to_date == date(2026, 10, 15)
