import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import permissions
from app.core.security import create_access_token
from app.modules.auth.errors import AuthError
from app.modules.users.models import User


def test_platform_admin_allowed_without_tenant(monkeypatch):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    session = Mock()
    session.get.return_value = SimpleNamespace(is_platform_admin=True)

    check_user_and_session = Mock()
    monkeypatch.setattr(permissions.tenancy, "_check_user_and_session", check_user_and_session)

    result = permissions.require_platform_admin(
        authorization=f"Bearer {create_access_token(user_id, session_id)}",
        session=session,
    )

    check_user_and_session.assert_called_once_with(session, user_id, session_id, ["pwd"])
    assert result.user_id == user_id
    assert result.session_id == session_id
    assert not hasattr(result, "tenant_id")
    session.get.assert_called_once_with(User, user_id)


def test_non_platform_admin_is_forbidden(monkeypatch):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    session = Mock()
    session.get.return_value = SimpleNamespace(is_platform_admin=False)

    check_user_and_session = Mock()
    monkeypatch.setattr(permissions.tenancy, "_check_user_and_session", check_user_and_session)

    with pytest.raises(AuthError) as exc:
        permissions.require_platform_admin(
            authorization=f"Bearer {create_access_token(user_id, session_id)}",
            session=session,
        )

    assert exc.value.status_code == 403
    check_user_and_session.assert_called_once_with(session, user_id, session_id, ["pwd"])
