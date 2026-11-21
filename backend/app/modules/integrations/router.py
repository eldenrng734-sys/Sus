import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import require_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.integrations import meta, service
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
    """Connect an integration. Write-only credentials; never logged or returned.

    Meta additionally subscribes the app to the Page's ``leadgen``, ``messages``
    and ``messaging_postbacks`` fields. Required Meta permissions:
    ``leads_retrieval``, ``ads_management``, ``pages_manage_metadata``.
    """
    if provider == "meta" and not body.provider_account_id.isdigit():
        raise AuthError(400, "validation_error", "Meta page id must be numeric")

    # Soft token validation: attempt a cheap Graph API call but do not block
    # connecting if it fails. The token scope (pages_read_engagement) required
    # by the old /{page_id} endpoint may not be granted; the token's real
    # validity is proven when the first webhook event arrives.
    # Hard-fail only for explicit 401 Unauthorized (bad/expired token).
    if settings.app_env != "test":
        import logging as _log
        try:
            await service.validate_meta_token(
                provider,
                body.provider_account_id,
                body.access_token,
            )
        except Exception as _val_exc:
            from app.modules.auth.errors import AuthError as _AE
            # Re-raise only if the token is explicitly invalid (401).
            # 400 or 403 likely means a missing scope, not a bad token.
            if isinstance(_val_exc, _AE) and getattr(_val_exc, "status_code", 0) == 400:
                _log.getLogger(__name__).warning(
                    "meta_token_soft_validation_failed provider=%s — scope may be missing; "
                    "proceeding with connect. Error: %s",
                    provider, _val_exc,
                )
            else:
                raise

    integration = service.connect_integration(
        session=session,
        context=context,
        provider=provider,
        provider_account_id=body.provider_account_id,
        access_token=body.access_token,
        waba_id=body.waba_id,
        scopes=body.scopes,
    )

    if provider == "meta":
        # Credentials are stored first: a temporary Graph failure must not lose
        # the token the admin just supplied. Re-running connect retries the
        # idempotent subscription.
        # subscribe_page requires pages_manage_metadata scope. If that scope is
        # missing the page may already be subscribed via the Meta App Dashboard,
        # so we log a warning but do not fail the connect flow.
        try:
            await meta.subscribe_page(
                body.provider_account_id,
                body.access_token,
            )
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "meta.subscribe_page failed for page_id=%s — "
                "page may already be subscribed or missing pages_manage_metadata scope; "
                "integration credentials were saved successfully.",
                body.provider_account_id,
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
