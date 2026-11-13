from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.errors import AuthError
from app.modules.tenants.models import Team


def _team_data(team: Team) -> dict:
    return {
        "id": str(team.id),
        "name": team.name,
        "created_at": team.created_at,
        "updated_at": team.updated_at,
    }


def list_teams(session: Session, context) -> list[dict]:
    statement = select(Team).where(Team.tenant_id == context.tenant_id)

    if context.role != "admin":
        if context.team_id is None:
            return []
        statement = statement.where(Team.id == context.team_id)

    teams = session.scalars(statement.order_by(Team.name)).all()
    return [_team_data(team) for team in teams]


def create_team(session: Session, context, name: str) -> dict:
    existing = session.scalar(
        select(Team).where(
            Team.tenant_id == context.tenant_id,
            Team.name == name,
        )
    )
    if existing:
        raise AuthError(409, "duplicate_name", "A team with this name already exists")

    team = Team(tenant_id=context.tenant_id, name=name)
    session.add(team)

    try:
        session.commit()
        session.refresh(team)
    except IntegrityError:
        session.rollback()
        raise AuthError(409, "duplicate_name", "A team with this name already exists")

    return _team_data(team)


def rename_team(session: Session, context, team_id, name: str) -> dict:
    team = session.scalar(
        select(Team).where(
            Team.id == team_id,
            Team.tenant_id == context.tenant_id,
        )
    )
    if team is None:
        raise AuthError(404, "not_found", "Team not found")

    existing = session.scalar(
        select(Team).where(
            Team.tenant_id == context.tenant_id,
            Team.name == name,
            Team.id != team_id,
        )
    )
    if existing:
        raise AuthError(409, "duplicate_name", "A team with this name already exists")

    team.name = name

    try:
        session.commit()
        session.refresh(team)
    except IntegrityError:
        session.rollback()
        raise AuthError(409, "duplicate_name", "A team with this name already exists")

    return _team_data(team)
