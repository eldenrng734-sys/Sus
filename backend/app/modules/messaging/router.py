from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.messaging import service
from app.modules.messaging.schemas import MessageSendRequest

router = APIRouter(prefix="/api/v1", tags=["messages"])


@router.post("/messages")
async def send_message(
    body: MessageSendRequest,
    response: Response,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128),
    ] = None,
) -> dict:
    """Send a WhatsApp text or approved template and return the stored message."""
    data, replay = await service.send_message(
        session,
        context,
        body,
        idempotency_key=idempotency_key or None,
    )
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return {"data": data}
