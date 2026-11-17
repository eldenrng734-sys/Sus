import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.tenancy import get_tenant_context
from app.database.session import get_session
from app.main import app
from app.modules.invitations import service


@pytest.fixture
def restore_overrides():
    original = app.dependency_overrides.copy()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original)


def _context(role: str):
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role=role,
        team_id=None,
        session_id=uuid.uuid4(),
    )


def test_invitation_routes_are_registered():
    paths = app.openapi()["paths"]

    assert "/api/v1/invitations" in paths
    assert "/api/v1/invitations/accept" in paths
    assert "/api/v1/memberships/{membership_id}/deactivate" in paths
    assert "/api/v1/memberships/{membership_id}/role" in paths


def test_invite_requires_tenant_admin_context(monkeypatch, restore_overrides):
    context = _context("admin")
    membership = SimpleNamespace(
        id=context.membership_id,
        tenant_id=context.tenant_id,
        role="admin",
        is_active=True,
    )
    session = Mock()
    session.get.return_value = membership
    create_invitation = Mock(return_value={"id": str(uuid.uuid4())})
    monkeypatch.setattr(service, "create_invitation", create_invitation)
    app.dependency_overrides[get_tenant_context] = lambda: context
    app.dependency_overrides[get_session] = lambda: session

    response = TestClient(app).post(
        "/api/v1/invitations",
        json={"email": "new@example.com", "role": "rep"},
    )

    assert response.status_code == 201
    create_invitation.assert_called_once()
    assert create_invitation.call_args.args[1] is membership


def test_invite_rejects_non_admin_context(monkeypatch, restore_overrides):
    app.dependency_overrides[get_tenant_context] = lambda: _context("rep")
    create_invitation = Mock()
    monkeypatch.setattr(service, "create_invitation", create_invitation)

    response = TestClient(app).post(
        "/api/v1/invitations",
        json={"email": "new@example.com", "role": "rep"},
    )

    assert response.status_code == 403
    create_invitation.assert_not_called()
