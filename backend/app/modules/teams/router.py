import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_admin, require_any_member
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.teams import service
from app.modules.teams.schemas import TeamCreate, TeamUpdate

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.get("")
def get_teams(
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.list_teams(session, context)}


@router.post("", status_code=201)
def post_team(
    body: TeamCreate,
    context: Annotated[TenantContext, Depends(require_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.create_team(session, context, body.name)}


@router.patch("/{team_id}")
def patch_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    context: Annotated[TenantContext, Depends(require_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.rename_team(session, context, team_id, body.name)}
