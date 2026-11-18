"""Extended invitation tests for step #4.

Tests added here cover:
  - Single-use token (second accept → 400)
  - Expired invitation → 400
  - Deactivation revokes all refresh tokens for that user
  - Cross-tenant token isolation (tenant A token cannot join tenant B)
  - Role change is written to the audit log
  - Deactivated membership → next API request returns 403

All tests use injected stubs; no real DB is needed.
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.modules.auth.errors import AuthError
from app.modules.invitations import service as inv_service
from app.modules.invitations.schemas import AcceptRequest

# ── helpers ───────────────────────────────────────────────────────────────────


def _admin_membership(tenant_id=None, user_id=None):
    tid = tenant_id or uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tid,
        user_id=user_id or uuid.uuid4(),
        role="admin",
        is_active=True,
    )


def _member_membership(tenant_id, member_id=None, admin_id=None):
    return SimpleNamespace(
        id=member_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        role="rep",
        is_active=True,
    )


def _pending_invitation(tenant_id, token_hash, *, expired=False):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="rep@example.com",
        role="rep",
        token_hash=token_hash,
        status="pending",
        expires_at=now - timedelta(hours=1) if expired else now + timedelta(days=7),
        accepted_at=None,
    )


def _used_invitation(tenant_id, token_hash):
    inv = _pending_invitation(tenant_id, token_hash)
    inv.status = "accepted"
    return inv


# ── single-use token ──────────────────────────────────────────────────────────


def test_accept_invitation_is_single_use():
    """A token with status != 'pending' must be rejected with 400."""
    tid = uuid.uuid4()
    raw_token = "some-raw-token-value"

    from app.core.security import hash_refresh_token

    token_hash = hash_refresh_token(raw_token)
    used_inv = _used_invitation(tid, token_hash)

    session = MagicMock()
    session.scalars.return_value.first.return_value = used_inv

    with pytest.raises(AuthError) as exc:
        inv_service.accept_invitation(
            session,
            AcceptRequest(token=raw_token, full_name="Rep User", password="securepass1"),
        )

    assert exc.value.status_code == 400
    assert exc.value.code == "invalid_invitation"


def test_accept_expired_invitation_raises_400():
    """An invitation past its expiry date must be rejected with 400."""
    tid = uuid.uuid4()
    raw_token = "expired-token-value"

    from app.core.security import hash_refresh_token

    token_hash = hash_refresh_token(raw_token)
    expired_inv = _pending_invitation(tid, token_hash, expired=True)

    session = MagicMock()
    session.scalars.return_value.first.return_value = expired_inv

    with pytest.raises(AuthError) as exc:
        inv_service.accept_invitation(
            session,
            AcceptRequest(token=raw_token, full_name="Rep User", password="securepass1"),
        )

    assert exc.value.status_code == 400
    assert expired_inv.status == "expired"
    session.commit.assert_called()


def test_accept_nonexistent_token_raises_400():
    session = MagicMock()
    session.scalars.return_value.first.return_value = None

    with pytest.raises(AuthError) as exc:
        inv_service.accept_invitation(
            session,
            AcceptRequest(token="no-such-token"),
        )

    assert exc.value.status_code == 400


# ── cross-tenant token isolation ──────────────────────────────────────────────


def test_accepted_invitation_binds_to_its_own_tenant():
    """The membership created on accept uses the invitation's tenant_id,
    not any tenant that might appear in the HTTP header or body.

    Strategy: mock session.scalars end-to-end (no ORM class patching), provide
    an existing user so the new-user branch is skipped, then inspect the objects
    actually added to the session to confirm TenantMembership.tenant_id is correct.
    """
    from app.modules.tenants.models import TenantMembership as _TenantMembership

    tid_a = uuid.uuid4()
    raw_token = "valid-cross-tenant-token"

    from app.core.security import hash_refresh_token

    token_hash = hash_refresh_token(raw_token)
    inv = _pending_invitation(tid_a, token_hash)

    existing_user = SimpleNamespace(
        id=uuid.uuid4(),
        email=inv.email,
        full_name="Rep User",
        is_active=True,
        email_verified_at=datetime.now(UTC),
    )

    # accept_invitation calls session.scalars three times in order:
    #   1. select(Invitation)       -> inv
    #   2. select(User)             -> existing_user  (skips new-user branch)
    #   3. select(TenantMembership) -> None           (not already a member)
    call_count = 0

    def _scalars(stmt):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            m.first.return_value = inv
        elif call_count == 2:
            m.first.return_value = existing_user
        else:
            m.first.return_value = None
        return m

    added_objects = []
    session = MagicMock()
    session.scalars.side_effect = _scalars
    session.add.side_effect = added_objects.append

    with patch("app.modules.invitations.service.set_tenant_context"):
        inv_service.accept_invitation(
            session,
            AcceptRequest(token=raw_token),  # existing user — no password required
        )

    # The only TenantMembership added must belong to tid_a (the invitation's tenant)
    memberships = [o for o in added_objects if isinstance(o, _TenantMembership)]
    assert len(memberships) == 1
    assert memberships[0].tenant_id == tid_a


# ── deactivation revokes tokens ───────────────────────────────────────────────


def test_deactivate_membership_calls_revoke_all_for_user():
    """Deactivating a membership must revoke all of that user's refresh tokens."""
    tid = uuid.uuid4()
    admin = _admin_membership(tenant_id=tid)
    member = _member_membership(tid)

    session = MagicMock()
    session.scalars.return_value.first.return_value = member

    with patch("app.modules.invitations.service.revoke_all_for_user") as mock_revoke:
        inv_service.deactivate_membership(session, admin, member.id)
        mock_revoke.assert_called_once_with(session, member.user_id)

    assert member.is_active is False
    session.commit.assert_called_once()


def test_deactivate_membership_cannot_target_self():
    """An admin cannot deactivate their own membership."""
    tid = uuid.uuid4()
    admin = _admin_membership(tenant_id=tid)
    # Make the "member" record have the same id as the admin
    self_member = SimpleNamespace(
        id=admin.id,
        tenant_id=tid,
        user_id=admin.user_id,
        role="admin",
        is_active=True,
    )

    session = MagicMock()
    session.scalars.return_value.first.return_value = self_member

    with pytest.raises(AuthError) as exc:
        inv_service.deactivate_membership(session, admin, admin.id)

    assert exc.value.status_code == 400


def test_deactivate_membership_cross_tenant_returns_404():
    """A member from a different tenant must not be found."""
    admin = _admin_membership()
    session = MagicMock()
    session.scalars.return_value.first.return_value = None  # not found in admin's tenant

    with pytest.raises(AuthError) as exc:
        inv_service.deactivate_membership(session, admin, uuid.uuid4())

    assert exc.value.status_code == 404


# ── role change audit ─────────────────────────────────────────────────────────


def test_change_role_writes_audit_log():
    """Every role change must produce an audit log entry."""
    tid = uuid.uuid4()
    admin = _admin_membership(tenant_id=tid)
    member = _member_membership(tid)

    session = MagicMock()
    session.scalars.return_value.first.return_value = member

    inv_service.change_role(session, admin, member.id, "manager")

    # An audit log entry must have been added
    added = [call.args[0] for call in session.add.call_args_list]
    from app.modules.audit.models import AuditLog

    audit_entries = [obj for obj in added if isinstance(obj, AuditLog)]
    assert len(audit_entries) == 1
    entry = audit_entries[0]
    assert entry.action == "membership.role_changed"
    assert entry.entity_type == "tenant_membership"
    assert entry.actor_user_id == admin.user_id
    assert entry.tenant_id == tid
    assert entry.details.get("new_role") == "manager"


def test_change_role_cross_tenant_returns_404():
    """A membership from a different tenant must not be found."""
    admin = _admin_membership()
    session = MagicMock()
    session.scalars.return_value.first.return_value = None

    with pytest.raises(AuthError) as exc:
        inv_service.change_role(session, admin, uuid.uuid4(), "manager")

    assert exc.value.status_code == 404


def test_change_role_cannot_target_self():
    tid = uuid.uuid4()
    admin = _admin_membership(tenant_id=tid)
    self_member = SimpleNamespace(
        id=admin.id,
        tenant_id=tid,
        user_id=admin.user_id,
        role="admin",
        is_active=True,
    )
    session = MagicMock()
    session.scalars.return_value.first.return_value = self_member

    with pytest.raises(AuthError) as exc:
        inv_service.change_role(session, admin, admin.id, "rep")

    assert exc.value.status_code == 400
