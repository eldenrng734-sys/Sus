import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.modules.auth.errors import AuthError
from app.modules.users import service
from app.modules.users.schemas import UserProfileUpdate


def make_context():
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
    )


def make_user(context):
    return SimpleNamespace(
        id=context.user_id,
        email="member@example.com",
        full_name="Old Name",
        is_active=True,
    )


def make_membership(context, tenant_id=None, active=True):
    return SimpleNamespace(
        id=context.membership_id,
        tenant_id=tenant_id or context.tenant_id,
        team_id=None,
        role="rep",
        is_active=active,
    )


def test_profile_update_trims_display_name():
    body = UserProfileUpdate(display_name="  New Name  ")
    assert body.display_name == "New Name"


def test_profile_update_rejects_blank_name():
    with pytest.raises(ValidationError):
        UserProfileUpdate(display_name="   ")


def test_get_current_user_returns_profile():
    context = make_context()
    user = make_user(context)
    membership = make_membership(context)

    session = MagicMock()
    session.get.side_effect = [user, membership]

    result = service.get_current_user(session, context)

    assert result["id"] == str(user.id)
    assert result["email"] == user.email
    assert result["display_name"] == "Old Name"
    assert result["role"] == "rep"
    assert result["is_active"] is True


def test_get_current_user_rejects_membership_from_another_tenant():
    context = make_context()
    user = make_user(context)
    membership = make_membership(context, tenant_id=uuid.uuid4())

    session = MagicMock()
    session.get.side_effect = [user, membership]

    with pytest.raises(AuthError) as exc:
        service.get_current_user(session, context)

    assert exc.value.status_code == 404


def test_update_current_user_commits_valid_profile():
    context = make_context()
    user = make_user(context)
    membership = make_membership(context)

    session = MagicMock()
    session.get.side_effect = [user, membership]

    result = service.update_current_user(
        session, context, UserProfileUpdate(display_name="New Name")
    )

    assert user.full_name == "New Name"
    assert result["display_name"] == "New Name"
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(user)


def test_update_current_user_does_not_commit_for_wrong_tenant():
    context = make_context()
    user = make_user(context)
    membership = make_membership(context, tenant_id=uuid.uuid4())

    session = MagicMock()
    session.get.side_effect = [user, membership]

    with pytest.raises(AuthError) as exc:
        service.update_current_user(
            session, context, UserProfileUpdate(display_name="New Name")
        )

    assert exc.value.status_code == 404
    assert user.full_name == "Old Name"
    session.commit.assert_not_called()


def test_list_tenant_users_serializes_results():
    context = make_context()
    user = make_user(context)
    membership = make_membership(context)

    session = MagicMock()
    session.execute.return_value.all.return_value = [(user, membership)]

    result = service.list_tenant_users(session, context)

    assert len(result) == 1
    assert result[0]["id"] == str(user.id)
    assert result[0]["display_name"] == "Old Name"
    assert result[0]["role"] == "rep"
