"""Cross-tenant security and RLS isolation tests for Step #25 (Platform Admin).

Verifies the explicit requirements:
1. crm_app still cannot SELECT another tenant's leads.
2. Company admin gets 403 on platform admin authorization check.
3. A suspended tenant's users fail the per-request membership check with 403 tenant_suspended.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core import permissions, tenancy
from app.modules.auth.errors import AuthError
from app.modules.tenants.models import Tenant
from tests.cross_tenant.support import Seed, set_tenant


def test_crm_app_cannot_select_other_tenant_leads(
    app_engine: Engine,
    seed: Seed,
) -> None:
    """crm_app under Company A context cannot select Company B leads."""
    with app_engine.connect() as conn:
        set_tenant(conn, seed.a.id)
        # Select all visible leads in Company A
        visible_leads = conn.execute(
            text("SELECT id, tenant_id FROM leads")
        ).fetchall()

        # Every visible lead must belong to Company A, none to Company B
        for lead in visible_leads:
            assert lead.tenant_id == seed.a.id
            assert lead.tenant_id != seed.b.id


def test_company_admin_rejected_from_platform_admin(
    app_engine: Engine,
    seed: Seed,
) -> None:
    """Company A admin is NOT a platform admin and must receive 403 forbidden."""
    admin_a_id = seed.a.users["admin"][0]

    with app_engine.connect() as conn:
        with Session(bind=conn) as session:
            # Fake claims for Company A admin
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    tenancy,
                    "_claims",
                    lambda auth: (admin_a_id, uuid.uuid4(), ["pwd", "totp"]),
                )
                mp.setattr(tenancy, "_check_user_and_session", lambda *args: None)

                with pytest.raises(AuthError) as exc_info:
                    permissions.require_platform_admin(
                        authorization="Bearer company-admin-token",
                        session=session,
                    )
                assert exc_info.value.status_code == 403
                assert exc_info.value.code == "forbidden"


def test_suspended_tenant_blocks_all_member_requests(
    admin_engine: Engine,
    app_engine: Engine,
    seed: Seed,
) -> None:
    """When a tenant is suspended, all membership requests return 403 tenant_suspended."""
    rep_a_id = seed.a.users["rep"][0]

    # 1. Suspend Company A via admin connection
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE tenants SET status = 'suspended' WHERE id = :id"),
            {"id": seed.a.id},
        )

    try:
        # 2. Verify that rep from Company A is blocked with 403 tenant_suspended
        with app_engine.connect() as conn:
            with Session(bind=conn) as session:
                with pytest.MonkeyPatch.context() as mp:
                    mp.setattr(
                        tenancy,
                        "_claims",
                        lambda auth: (rep_a_id, uuid.uuid4(), ["pwd", "totp"]),
                    )
                    mp.setattr(tenancy, "_check_user_and_session", lambda *args: None)

                    with pytest.raises(AuthError) as exc_info:
                        tenancy.get_tenant_context(
                            x_tenant_id=str(seed.a.id),
                            authorization="Bearer rep-token",
                            session=session,
                        )
                    assert exc_info.value.status_code == 403
                    assert exc_info.value.code == "tenant_suspended"
    finally:
        # 3. Clean up: restore Company A to active
        with admin_engine.begin() as conn:
            conn.execute(
                text("UPDATE tenants SET status = 'active' WHERE id = :id"),
                {"id": seed.a.id},
            )
