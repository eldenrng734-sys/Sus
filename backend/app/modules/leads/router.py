import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.leads import service
from app.modules.leads.schemas import LeadAssignRequest

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


@router.post("/{lead_id}/assign")
def post_assign_lead(
    lead_id: uuid.UUID,
    body: LeadAssignRequest,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.assign_lead(session, context, lead_id, body)}
