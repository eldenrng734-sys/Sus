from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext, get_tenant_context
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.settings import service
from app.modules.settings.schemas import (
    AutomationSettingsResponse,
    AutomationSettingsUpdate,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/automation")
def get_automation_settings(
    context: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_session),
) -> dict:
    if context.role != "admin":
        raise AuthError(403, "forbidden", "Admin access required")

    tenant_settings = service.get_tenant_settings(session, context.tenant_id)
    if tenant_settings is None:
        data = AutomationSettingsResponse(
            timezone=service.DEFAULT_TIMEZONE,
            quiet_hours_start=service.DEFAULT_QUIET_HOURS_START.strftime("%H:%M"),
            quiet_hours_end=service.DEFAULT_QUIET_HOURS_END.strftime("%H:%M"),
        )
    else:
        data = AutomationSettingsResponse(
            timezone=tenant_settings.timezone,
            quiet_hours_start=tenant_settings.quiet_hours_start.strftime("%H:%M"),
            quiet_hours_end=tenant_settings.quiet_hours_end.strftime("%H:%M"),
        )
    return {"data": data.model_dump()}


@router.put("/automation")
def put_automation_settings(
    body: AutomationSettingsUpdate,
    context: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_session),
) -> dict:
    if context.role != "admin":
        raise AuthError(403, "forbidden", "Admin access required")

    updated = service.update_automation_settings(
        session=session,
        tenant_id=context.tenant_id,
        data=body,
        user_id=context.user_id,
    )
    session.commit()
    data = AutomationSettingsResponse(
        timezone=updated.timezone,
        quiet_hours_start=updated.quiet_hours_start.strftime("%H:%M"),
        quiet_hours_end=updated.quiet_hours_end.strftime("%H:%M"),
    )
    return {"data": data.model_dump()}
