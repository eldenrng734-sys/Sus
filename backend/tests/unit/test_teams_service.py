from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest
from pydantic import ValidationError

from app.modules.auth.errors import AuthError
from app.modules.teams import service
from app.modules.teams.schemas import TeamCreate, TeamUpdate


def make_context(role="admin", team_id=None):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
    )


def test_list_teams_returns_empty_for_member_without_team():
    session = MagicMock()
    context = make_context(role="rep", team_id=None)

    result = service.list_teams(session, context)

    assert result == []
    session.scalars.assert_not_called()


def test_list_teams_returns_team_data():
    session = MagicMock()
    context = make_context()
    team = SimpleNamespace(
        id=uuid.uuid4(),
        name="Dhaka Sales",
        created_at=None,
        updated_at=None,
    )
    session.scalars.return_value.all.return_value = [team]

    result = service.list_teams(session, context)

    assert result == [{
        "id": str(team.id),
        "name": "Dhaka Sales",
        "created_at": None,
        "updated_at": None,
    }]


def test_create_team_rejects_duplicate_name():
    session = MagicMock()
    session.scalar.return_value = object()

    with pytest.raises(AuthError) as exc:
        service.create_team(session, make_context(), "Dhaka Sales")

    assert exc.value.status_code == 409
    assert exc.value.code == "duplicate_name"
    session.add.assert_not_called()


def test_rename_team_returns_404_for_unknown_team():
    session = MagicMock()
    session.scalar.return_value = None

    with pytest.raises(AuthError) as exc:
        service.rename_team(session, make_context(), uuid.uuid4(), "New Name")

    assert exc.value.status_code == 404
    assert exc.value.code == "not_found"


def test_team_name_is_trimmed():
    assert TeamCreate(name="  Dhaka Sales  ").name == "Dhaka Sales"
    assert TeamUpdate(name="  Chattogram Sales  ").name == "Chattogram Sales"


@pytest.mark.parametrize("schema", [TeamCreate, TeamUpdate])
def test_team_name_cannot_be_blank(schema):
    with pytest.raises(ValidationError):
        schema(name="   ")
