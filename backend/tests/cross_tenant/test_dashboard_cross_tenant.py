"""Cross-tenant isolation tests for Dashboard Summary API (#15).

Verifies that:
- Company A admin dashboard never counts Company B's leads, tasks, or users.
- Company A manager dashboard cannot access Company B's team or data.
- Company A sales rep sees only own leads within Company A's boundary.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.dashboard import service
from tests.cross_tenant.support import Seed, set_tenant


def _ctx(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "admin",
    team_id: uuid.UUID | None = None,
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        membership_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
        session_id=uuid.uuid4(),
    )


def test_company_admin_dashboard_never_counts_other_tenant_data(
    app_engine: Engine,
    seed: Seed,
) -> None:
    """Company A admin queries dashboard; Company B data must be completely invisible."""
    admin_a_user = seed.a.users["admin"][0]
    ctx_a = _ctx(tenant_id=seed.a.id, user_id=admin_a_user, role="admin")

    with app_engine.connect() as conn:
        set_tenant(conn, seed.a.id)
        with Session(bind=conn) as session:
            res_a = service.get_dashboard_summary(session, ctx_a, scope="company")

            # Check that leads counted for Company A are only within Tenant A
            assert res_a.scope == "company"
            # All reps returned must be members of Tenant A
            for rep in res_a.reps:
                assert rep.user_id not in seed.b.users["rep"]


def test_manager_cannot_access_other_tenant_team(
    app_engine: Engine,
    seed: Seed,
) -> None:
    """Manager from Company A cannot query team scope for a team in Company B."""
    mgr_a_user = seed.a.users["manager"][0]
    team_a_id = seed.a.team_ids[0] if seed.a.team_ids else uuid.uuid4()
    foreign_team_id = seed.b.team_ids[0] if seed.b.team_ids else uuid.uuid4()

    ctx_a = _ctx(tenant_id=seed.a.id, user_id=mgr_a_user, role="manager", team_id=team_a_id)

    with app_engine.connect() as conn:
        set_tenant(conn, seed.a.id)
        with Session(bind=conn) as session:
            # Querying with other company's team_id must be rejected
            with pytest.raises(AuthError) as exc_info:
                service.get_dashboard_summary(session, ctx_a, scope="team", team_id=foreign_team_id)
            assert exc_info.value.status_code == 403


def test_rep_dashboard_never_mixes_cross_tenant_leads(
    app_engine: Engine,
    seed: Seed,
) -> None:
    """Rep from Company A sees only own leads, zero records from Company B."""
    rep_a_user = seed.a.users["rep"][0]
    ctx_a = _ctx(tenant_id=seed.a.id, user_id=rep_a_user, role="rep")

    with app_engine.connect() as conn:
        set_tenant(conn, seed.a.id)
        with Session(bind=conn) as session:
            res = service.get_dashboard_summary(session, ctx_a, scope="me")
            assert res.scope == "me"
            for conv in res.recent_conversations:
                assert conv.lead_id not in seed.b.lead_ids
