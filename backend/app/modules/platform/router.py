import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import PlatformAdminContext, require_platform_admin
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.platform import service
from app.modules.platform.schemas import (
    PlatformHealthResponse,
    TenantDetailResponse,
    TenantListResponse,
    TenantSummary,
    TenantUpdateRequest,
)

router = APIRouter(
    prefix="/api/v1/platform",
    tags=["platform admin"],
)


@router.get("/tenants", response_model=TenantListResponse)
def list_tenants(
    admin_ctx: Annotated[PlatformAdminContext, Depends(require_platform_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """List tenants with member count and status summary."""
    tenants = service.list_tenants(session)
    return {
        "data": [TenantSummary.model_validate(t).model_dump() for t in tenants]
    }


@router.get("/tenants/{tenant_id}", response_model=TenantDetailResponse)
def get_tenant(
    tenant_id: uuid.UUID,
    admin_ctx: Annotated[PlatformAdminContext, Depends(require_platform_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """Get single tenant summary including member count."""
    tenant = service.get_tenant(session, tenant_id)
    if tenant is None:
        raise AuthError(404, "not_found", "Tenant not found")
    return {"data": TenantSummary.model_validate(tenant).model_dump()}


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantDetailResponse)
def suspend_tenant(
    tenant_id: uuid.UUID,
    admin_ctx: Annotated[PlatformAdminContext, Depends(require_platform_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """Suspend a tenant. Users of a suspended tenant immediately fail authorization checks."""
    tenant = service.suspend_tenant(
        session=session,
        tenant_id=tenant_id,
        actor_user_id=admin_ctx.user_id,
    )
    if tenant is None:
        raise AuthError(404, "not_found", "Tenant not found")
    session.commit()
    return {"data": TenantSummary.model_validate(tenant).model_dump()}


@router.patch("/tenants/{tenant_id}", response_model=TenantDetailResponse)
def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdateRequest,
    admin_ctx: Annotated[PlatformAdminContext, Depends(require_platform_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """Update tenant status ('active' or 'suspended')."""
    tenant = service.update_tenant_status(
        session=session,
        tenant_id=tenant_id,
        status=body.status,
        actor_user_id=admin_ctx.user_id,
    )
    if tenant is None:
        raise AuthError(404, "not_found", "Tenant not found")
    session.commit()
    return {"data": TenantSummary.model_validate(tenant).model_dump()}


@router.get("/health", response_model=PlatformHealthResponse)
def get_platform_health(
    admin_ctx: Annotated[PlatformAdminContext, Depends(require_platform_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """Get platform database connections and dead outbox event count across all tenants."""
    health_data = service.get_platform_health(session)
    return {"data": health_data}
