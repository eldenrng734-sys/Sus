import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.service_auth import InternalServiceContext, require_internal_service
from app.core.tenancy import TenantContext, get_tenant_context
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.notifications import crud, service
from app.modules.notifications.schemas import (
    NotificationCreateRequest,
    NotificationListResponse,
    NotificationOut,
)

# 1. Internal automation router for n8n workers
internal_router = APIRouter(prefix="/internal/v1/automation", tags=["internal automation"])


@internal_router.post("/notifications", status_code=202)
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


# 2. User notifications router for notification bell & inbox
router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_user_notifications(
    read: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_session),
) -> dict:
    """List tenant-scoped notifications for the current authenticated user."""
    items = crud.list_notifications(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        read=read,
        limit=limit,
    )
    unread_count = crud.count_unread(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
    )
    return {
        "data": [NotificationOut.model_validate(item).model_dump() for item in items],
        "meta": {"unread_count": unread_count},
    }


@router.patch("/{notification_id}/read", response_model=dict)
def mark_notification_read(
    notification_id: uuid.UUID,
    context: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_session),
) -> dict:
    """Mark a user's notification as read. User sees and marks only their own."""
    notification = crud.mark_read(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        notification_id=notification_id,
    )
    if notification is None:
        raise AuthError(404, "not_found", "Notification not found")
    session.commit()
    return {"data": NotificationOut.model_validate(notification).model_dump()}


@router.post("/mark-all-read", response_model=dict)
def mark_all_user_notifications_read(
    context: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_session),
) -> dict:
    """Mark all unread notifications as read for current user."""
    count = crud.mark_all_read(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
    )
    session.commit()
    return {"data": {"marked_count": count}}
