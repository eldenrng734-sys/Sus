from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.service_auth import InternalServiceContext, require_internal_service
from app.database.session import get_session
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationCreateRequest

router = APIRouter(prefix="/internal/v1/automation", tags=["internal automation"])


@router.post("/notifications", status_code=202)
def create_notification(
    request: Request,
    context: InternalServiceContext = Depends(require_internal_service),
    session: Session = Depends(get_session),
) -> Response:
    try:
        payload = NotificationCreateRequest.model_validate_json(request.state.internal_raw_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    service.create_notification(session, context, payload)
    return Response(status_code=202)
