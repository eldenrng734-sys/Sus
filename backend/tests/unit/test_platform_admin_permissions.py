import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import permissions
from app.modules.auth.errors import AuthError
from app.modules.users.models import User


def test_platform_admin_allowed_without_tenant(monkeypatch):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    session = Mock()
    session.get.return_value = SimpleNamespace(is_platform_admin=True)

    monkeypatch.setattr(
        permissions.tenancy,
        "_claims",
        lambda authorization: (user_id, session_id),
    )
    monkeypatch.setattr(
        permissions.tenancy,
        "_check_user_and_session",
        lambda db, uid, sid: None,
    )

    result = permissions.require_platform_admin(
        authorization="Bearer test-token",
        session=session,
    )

    assert result.user_id == user_id
    assert result.session_id == session_id
    assert not hasattr(result, "tenant_id")
    session.get.assert_called_once_with(User, user_id)


def test_non_platform_admin_is_forbidden(monkeypatch):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    session = Mock()
    session.get.return_value = SimpleNamespace(is_platform_admin=False)

    monkeypatch.setattr(
        permissions.tenancy,
        "_claims",
        lambda authorization: (user_id, session_id),
    )
    monkeypatch.setattr(
        permissions.tenancy,
        "_check_user_and_session",
        lambda db, uid, sid: None,
    )

    with pytest.raises(AuthError) as exc:
        permissions.require_platform_admin(
            authorization="Bearer test-token",
            session=session,
        )

    assert exc.value.status_code == 403
