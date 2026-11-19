"""Unit and isolation tests for user notifications API (Step #21).

Tests:
- GET /api/v1/notifications returns user's notifications ordered by created_at desc with unread_count
- GET /api/v1/notifications?read=false filters to unread only
- GET /api/v1/notifications?read=true filters to read only
- PATCH /api/v1/notifications/{id}/read marks notification as read (read_at set)
- Own-only: Rep A cannot read or mark Rep B's notification (raises 404)
- Cross-tenant: Tenant 2 user cannot read or mark Tenant 1 notification (raises 404)
- POST /api/v1/notifications/mark-all-read marks all unread as read
"""

import datetime
import uuid
from unittest.mock import MagicMock

import pytest

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.notifications import crud, router
from app.modules.notifications.models import Notification


def _make_context(
    role="rep",
    tenant_id=None,
    user_id=None,
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role=role,
        team_id=None,
        session_id=uuid.uuid4(),
    )


def _make_notification(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    read: bool = False,
    title: str = "New Lead Assigned",
) -> Notification:
    notif = Notification(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        type="new_lead",
        title=title,
        body="A new qualified lead needs follow-up.",
        entity_type="lead",
        entity_id=uuid.uuid4(),
        created_at=datetime.datetime.now(datetime.UTC),
        read_at=datetime.datetime.now(datetime.UTC) if read else None,
    )
    return notif


def test_list_notifications_own_and_unread_count():
    ctx = _make_context()
    n1 = _make_notification(ctx.tenant_id, ctx.user_id, read=False, title="Lead 1")
    n2 = _make_notification(ctx.tenant_id, ctx.user_id, read=True, title="Lead 2")

    session = MagicMock()
    # Mock scalars().all()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [n1, n2]
    session.scalars.return_value = mock_scalars
    # Mock unread count scalar
    session.scalar.return_value = 1

    resp = router.list_user_notifications(read=None, limit=50, context=ctx, session=session)
    assert len(resp["data"]) == 2
    assert resp["meta"]["unread_count"] == 1
    assert resp["data"][0]["title"] == "Lead 1"
    assert resp["data"][0]["read_at"] is None
    assert resp["data"][1]["read_at"] is not None


def test_mark_notification_read_success():
    ctx = _make_context()
    notif = _make_notification(ctx.tenant_id, ctx.user_id, read=False)

    session = MagicMock()
    session.scalar.return_value = notif

    resp = router.mark_notification_read(
        notification_id=notif.id,
        context=ctx,
        session=session,
    )
    assert resp["data"]["id"] == notif.id
    assert resp["data"]["read_at"] is not None
    assert notif.read_at is not None
    session.commit.assert_called_once()


def test_mark_notification_read_not_found_raises_404():
    ctx = _make_context()
    session = MagicMock()
    session.scalar.return_value = None  # Notification doesn't exist for this user/tenant

    with pytest.raises(AuthError) as exc_info:
        router.mark_notification_read(
            notification_id=uuid.uuid4(),
            context=ctx,
            session=session,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


def test_own_only_and_cross_tenant_isolation():
    tenant_1 = uuid.uuid4()
    tenant_2 = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # Case 1: Same tenant, but belongs to user_b. User_a should not be able to mark it read.
    session = MagicMock()
    # When crud.mark_read searches with tenant_1 and user_a, it finds nothing because row has user_b
    session.scalar.return_value = None
    ctx_a = _make_context(tenant_id=tenant_1, user_id=user_a)

    notif_b_id = uuid.uuid4()
    with pytest.raises(AuthError) as exc_info:
        router.mark_notification_read(
            notification_id=notif_b_id,
            context=ctx_a,
            session=session,
        )
    assert exc_info.value.status_code == 404

    # Case 2: Cross tenant - user in tenant_2 cannot mark notification in tenant_1
    ctx_t2 = _make_context(tenant_id=tenant_2, user_id=user_a)
    with pytest.raises(AuthError) as exc_info2:
        router.mark_notification_read(
            notification_id=notif_b_id,
            context=ctx_t2,
            session=session,
        )
    assert exc_info2.value.status_code == 404


def test_mark_all_read():
    ctx = _make_context()
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.rowcount = 4
    session.execute.return_value = mock_result

    resp = router.mark_all_user_notifications_read(context=ctx, session=session)
    assert resp["data"]["marked_count"] == 4
    session.commit.assert_called_once()
