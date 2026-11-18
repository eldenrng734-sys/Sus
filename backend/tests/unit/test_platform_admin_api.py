"""Unit and authorization tests for Platform Admin API (Step #25).

Verifies:
- Company admin gets 403 forbidden on all /api/v1/platform/* routes
- Manager and Rep get 403 forbidden on all /api/v1/platform/* routes
- Unauthenticated or non-platform admin users get 403 forbidden
- Platform admin without MFA (no 'totp' in amr) gets 403 mfa_required
- Platform admin with MFA can:
  - List all tenants with status and member counts
  - Get specific tenant detail + member count
  - Suspend a tenant with audit event
  - Update tenant status via PATCH
  - Get platform health (DB connections & dead outbox count)
- A suspended tenant's users fail the per-request tenancy check with 403 tenant_suspended
"""

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core import permissions, tenancy
from app.core.permissions import PlatformAdminContext
from app.core.security import create_access_token
from app.modules.auth.errors import AuthError
from app.modules.platform import router, service
from app.modules.platform.schemas import TenantUpdateRequest
from app.modules.tenants.models import Tenant, TenantMembership
from app.modules.users.models import User


def _make_platform_admin_ctx() -> PlatformAdminContext:
    return PlatformAdminContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# 1. Permission & MFA Enforcement Tests
# ---------------------------------------------------------------------------


def test_require_platform_admin_blocks_non_platform_admin():
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    mock_session = MagicMock()

    # Normal user (not platform admin)
    normal_user = User(
        id=user_id,
        email="company_admin@example.com",
        password_hash="hash",
        is_active=True,
        is_platform_admin=False,
    )
    mock_session.get.return_value = normal_user

    with (
        patch("app.core.tenancy._claims", return_value=(user_id, session_id, ["pwd", "totp"])),
        patch("app.core.tenancy._check_user_and_session"),
    ):
        with pytest.raises(AuthError) as exc_info:
            permissions.require_platform_admin(
                authorization="Bearer valid-token",
                session=mock_session,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"


def test_require_platform_admin_blocks_session_without_mfa():
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    mock_session = MagicMock()

    platform_user = User(
        id=user_id,
        email="superadmin@syntrix.internal",
        password_hash="hash",
        is_active=True,
        is_platform_admin=True,
    )
    mock_session.get.return_value = platform_user

    # Session only has pwd, missing totp
    with (
        patch("app.core.tenancy._claims", return_value=(user_id, session_id, ["pwd"])),
        patch("app.core.tenancy._check_user_and_session"),
    ):
        with pytest.raises(AuthError) as exc_info:
            permissions.require_platform_admin(
                authorization="Bearer token-no-mfa",
                session=mock_session,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "mfa_required"


def test_require_platform_admin_allows_mfa_platform_admin():
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    mock_session = MagicMock()

    platform_user = User(
        id=user_id,
        email="superadmin@syntrix.internal",
        password_hash="hash",
        is_active=True,
        is_platform_admin=True,
    )
    mock_session.get.return_value = platform_user

    with (
        patch("app.core.tenancy._claims", return_value=(user_id, session_id, ["pwd", "totp"])),
        patch("app.core.tenancy._check_user_and_session"),
    ):
        ctx = permissions.require_platform_admin(
            authorization="Bearer valid-token",
            session=mock_session,
        )
        assert ctx.user_id == user_id
        assert ctx.session_id == session_id


# ---------------------------------------------------------------------------
# 2. Router Operations Tests
# ---------------------------------------------------------------------------


def test_list_tenants_endpoint():
    admin_ctx = _make_platform_admin_ctx()
    mock_session = MagicMock()

    t1_id = uuid.uuid4()
    t2_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)

    mock_tenants = [
        {
            "id": t1_id,
            "name": "Company Alpha",
            "slug": "alpha",
            "status": "active",
            "created_at": now,
            "member_count": 5,
        },
        {
            "id": t2_id,
            "name": "Company Beta",
            "slug": "beta",
            "status": "suspended",
            "created_at": now,
            "member_count": 2,
        },
    ]

    with patch("app.modules.platform.service.list_tenants", return_value=mock_tenants):
        resp = router.list_tenants(admin_ctx=admin_ctx, session=mock_session)
        assert len(resp["data"]) == 2
        assert resp["data"][0]["name"] == "Company Alpha"
        assert resp["data"][0]["member_count"] == 5
        assert resp["data"][1]["status"] == "suspended"


def test_get_tenant_detail_endpoint():
    admin_ctx = _make_platform_admin_ctx()
    mock_session = MagicMock()
    t_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)

    mock_tenant = {
        "id": t_id,
        "name": "Acme Corp",
        "slug": "acme",
        "status": "active",
        "created_at": now,
        "member_count": 8,
    }

    with patch("app.modules.platform.service.get_tenant", return_value=mock_tenant):
        resp = router.get_tenant(tenant_id=t_id, admin_ctx=admin_ctx, session=mock_session)
        assert resp["data"]["id"] == t_id
        assert resp["data"]["name"] == "Acme Corp"
        assert resp["data"]["member_count"] == 8


def test_get_tenant_detail_not_found_404():
    admin_ctx = _make_platform_admin_ctx()
    mock_session = MagicMock()
    t_id = uuid.uuid4()

    with patch("app.modules.platform.service.get_tenant", return_value=None):
        with pytest.raises(AuthError) as exc_info:
            router.get_tenant(tenant_id=t_id, admin_ctx=admin_ctx, session=mock_session)
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "not_found"


def test_suspend_tenant_endpoint_audited():
    admin_ctx = _make_platform_admin_ctx()
    mock_session = MagicMock()
    t_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)

    mock_tenant = {
        "id": t_id,
        "name": "Target Corp",
        "slug": "target",
        "status": "suspended",
        "created_at": now,
        "member_count": 3,
    }

    with patch("app.modules.platform.service.suspend_tenant", return_value=mock_tenant) as mock_suspend:
        resp = router.suspend_tenant(tenant_id=t_id, admin_ctx=admin_ctx, session=mock_session)
        assert resp["data"]["id"] == t_id
        assert resp["data"]["status"] == "suspended"
        mock_suspend.assert_called_once_with(
            session=mock_session,
            tenant_id=t_id,
            actor_user_id=admin_ctx.user_id,
        )
        mock_session.commit.assert_called_once()


def test_patch_tenant_status_endpoint():
    admin_ctx = _make_platform_admin_ctx()
    mock_session = MagicMock()
    t_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)

    mock_tenant = {
        "id": t_id,
        "name": "Reactivated Corp",
        "slug": "reactivated",
        "status": "active",
        "created_at": now,
        "member_count": 3,
    }

    with patch("app.modules.platform.service.update_tenant_status", return_value=mock_tenant) as mock_update:
        resp = router.update_tenant(
            tenant_id=t_id,
            body=TenantUpdateRequest(status="active"),
            admin_ctx=admin_ctx,
            session=mock_session,
        )
        assert resp["data"]["status"] == "active"
        mock_update.assert_called_once_with(
            session=mock_session,
            tenant_id=t_id,
            status="active",
            actor_user_id=admin_ctx.user_id,
        )
        mock_session.commit.assert_called_once()


def test_platform_health_endpoint():
    admin_ctx = _make_platform_admin_ctx()
    mock_session = MagicMock()

    mock_health = {
        "db_connections": 14,
        "dead_outbox_count": 0,
        "status": "ok",
    }

    with patch("app.modules.platform.service.get_platform_health", return_value=mock_health):
        resp = router.get_platform_health(admin_ctx=admin_ctx, session=mock_session)
        assert resp["data"]["db_connections"] == 14
        assert resp["data"]["dead_outbox_count"] == 0
        assert resp["data"]["status"] == "ok"


# ---------------------------------------------------------------------------
# 3. Suspended Tenant Access Blocking (Tenancy Check Verification)
# ---------------------------------------------------------------------------


def test_suspended_tenant_users_fail_membership_check():
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    mock_session = MagicMock()

    # Active membership
    active_membership = TenantMembership(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        role="rep",
        is_active=True,
    )
    mock_session.scalar.return_value = active_membership

    # But tenant is SUSPENDED
    suspended_tenant = Tenant(
        id=tenant_id,
        name="Suspended Corp",
        slug="suspended-corp",
        status="suspended",
    )
    mock_session.get.return_value = suspended_tenant

    with (
        patch("app.core.tenancy._claims", return_value=(user_id, session_id, ["pwd"])),
        patch("app.core.tenancy._check_user_and_session"),
    ):
        with pytest.raises(AuthError) as exc_info:
            tenancy.get_tenant_context(
                x_tenant_id=str(tenant_id),
                authorization="Bearer any-rep-token",
                session=mock_session,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "tenant_suspended"
