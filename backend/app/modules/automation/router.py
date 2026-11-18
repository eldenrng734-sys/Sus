"""Internal API for n8n. Reachable only on the private network, signed with HMAC.

Every endpoint takes one specific resource ID; there is deliberately no list-everything
route (API_CONTRACT.md section 14).
"""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.service_auth import InternalServiceContext, require_internal_service
from app.database.session import get_session
from app.modules.automation import service
from app.modules.automation.schemas import (
    AutomationErrorRequest,
    AutomationMessageSendRequest,
    TaskResultRequest,
)

router = APIRouter(prefix="/internal/v1/automation", tags=["internal automation"])


@router.get("/health")
def internal_health(
    context: InternalServiceContext = Depends(require_internal_service),
) -> dict:
    """Proves n8n can reach the API and that its signature is accepted."""
    return {"data": {"status": "ok", "service": context.service_id}}


@router.get("/leads/{lead_id}")
def get_lead_context(
    lead_id: uuid.UUID,
    context: InternalServiceContext = Depends(require_internal_service),
    session: Session = Depends(get_session),
) -> dict:
    data = service.get_lead_context(session, context, lead_id)
    return {"data": data}


@router.post("/leads/{lead_id}/assess")
def assess_lead(
    lead_id: uuid.UUID,
    context: InternalServiceContext = Depends(require_internal_service),
    session: Session = Depends(get_session),
) -> JSONResponse:
    status_code, resp = service.request_lead_assessment(session, context, lead_id)
    return JSONResponse(status_code=status_code, content=resp)


@router.post("/messages")
async def send_message(
    request: Request,
    context: InternalServiceContext = Depends(require_internal_service),
    session: Session = Depends(get_session),
) -> JSONResponse:
    raw_body = getattr(request.state, "internal_raw_body", b"")
    try:
        payload = AutomationMessageSendRequest.model_validate_json(raw_body or b"{}")
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    status_code, resp = await service.send_automation_message(session, context, payload)
    return JSONResponse(status_code=status_code, content=resp)


@router.post("/tasks/{task_id}/result")
def task_result(
    task_id: uuid.UUID,
    request: Request,
    context: InternalServiceContext = Depends(require_internal_service),
    session: Session = Depends(get_session),
) -> JSONResponse:
    raw_body = getattr(request.state, "internal_raw_body", b"")
    try:
        payload = TaskResultRequest.model_validate_json(raw_body or b"{}")
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    status_code, resp = service.record_task_result(session, context, task_id, payload)
    return JSONResponse(status_code=status_code, content=resp)


@router.post("/errors", status_code=202)
def report_error(
    request: Request,
    context: InternalServiceContext = Depends(require_internal_service),
    session: Session = Depends(get_session),
) -> JSONResponse:
    raw_body = getattr(request.state, "internal_raw_body", b"")
    try:
        payload = AutomationErrorRequest.model_validate_json(raw_body or b"{}")
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    status_code, resp = service.record_automation_error(session, context, payload)
    return JSONResponse(status_code=status_code, content=resp)
