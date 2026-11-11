import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.conversations import service
from app.modules.conversations.schemas import ConversationCreate, MessageCreate

router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.post("/conversations", status_code=201)
def create_conversation(
    body: ConversationCreate,
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.create_conversation(session, context, body)}


@router.get("/conversations")
def list_conversations(
    lead_id: uuid.UUID | None = None,
    status: Literal["open", "pending", "closed"] | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    data = service.list_conversations(session, context, lead_id, status, limit, offset)
    return {"data": data, "meta": {"limit": limit, "offset": offset}}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    data = service.list_messages(session, context, conversation_id, limit, offset)
    return {"data": data, "meta": {"limit": limit, "offset": offset}}


@router.post("/messages", status_code=201)
def send_message(
    body: MessageCreate,
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.send_message(session, context, body)}


@router.get("/leads/{lead_id}/timeline")
def lead_timeline(
    lead_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    context: TenantContext = Depends(require_any_member),
    session: Session = Depends(get_session),
) -> dict:
    data = service.get_timeline(session, context, lead_id, limit, offset)
    return {"data": data, "meta": {"limit": limit, "offset": offset}}
