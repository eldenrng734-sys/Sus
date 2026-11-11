import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member, require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.leads import crud, service
from app.modules.leads.schemas import LeadAssignRequest, LeadCreate, LeadUpdate, NoteCreate

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


@router.post("/{lead_id}/assign")
def post_assign_lead(
    lead_id: uuid.UUID,
    body: LeadAssignRequest,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.assign_lead(session, context, lead_id, body)}


@router.post("", status_code=201)
def post_lead(
    body: LeadCreate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": crud.create_lead(session, context, body)}


@router.get("")
def get_leads(
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    q: str | None = Query(default=None, max_length=100),
    status: str | None = None,
    priority: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    data, meta = crud.list_leads(session, context, q, status, priority, limit, cursor)
    return {"data": data, "meta": meta}


@router.get("/{lead_id}")
def get_lead_detail(
    lead_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": crud.get_lead(session, context, lead_id)}


@router.patch("/{lead_id}")
def patch_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": crud.update_lead(session, context, lead_id, body)}


@router.post("/{lead_id}/notes", status_code=201)
def post_note(
    lead_id: uuid.UUID,
    body: NoteCreate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": crud.add_note(session, context, lead_id, body)}
