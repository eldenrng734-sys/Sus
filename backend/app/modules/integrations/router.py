import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import require_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    ConnectIntegrationRequest,
    ConnectIntegrationResponse,
    DisconnectIntegrationResponse,
    IntegrationItem,
)

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["integrations"],
)


@router.post("/{provider}/connect", response_model=dict)
async def connect(
    provider: str,
    body: ConnectIntegrationRequest,
    context: Annotated[TenantContext, Depends(require_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """Connect an integration. Write-only credentials; never logged or returned."""
    # Cheap Graph API validation call on connect (unless explicitly in unit test bypass)
    if settings.app_env != "test":
        await service.validate_meta_token(
            provider,
            body.provider_account_id,
            body.access_token,
        )

    integration = service.connect_integration(
        session=session,
        context=context,
        provider=provider,
        provider_account_id=body.provider_account_id,
        access_token=body.access_token,
        waba_id=body.waba_id,
        scopes=body.scopes,
    )

    resp = ConnectIntegrationResponse(
        connected=True,
        id=integration.id,
        provider=integration.provider,
        provider_account_id=integration.provider_account_id,
        status=integration.status,
        scopes=integration.scopes,
    )
    return {"data": resp.model_dump()}


@router.get("", response_model=dict)
def list_connected(
    context: Annotated[TenantContext, Depends(require_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """List integrations for this company. Credentials are never returned."""
    integrations = service.list_integrations(session, context)
    items = [
        IntegrationItem(
            id=item.id,
            provider=item.provider,
            provider_account_id=item.provider_account_id,
            status=item.status,
            scopes=item.scopes,
            created_at=item.created_at,
            connected=(item.status == "active"),
        ).model_dump()
        for item in integrations
    ]
    return {"data": items}


@router.delete("/{integration_id}", response_model=dict)
def disconnect(
    integration_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_admin)],
    session: Session = Depends(get_session),
) -> dict:
    """Soft-disconnect an integration."""
    integration = service.disconnect_integration(session, context, integration_id)
    resp = DisconnectIntegrationResponse(
        connected=False,
        id=integration.id,
        status=integration.status,
    )
    return {"data": resp.model_dump()}

