import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tenancy import TenantContext
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.integrations.crypto import decrypt_credentials, encrypt_credentials
from app.modules.integrations.models import Integration

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"


class CredentialsNotFound(Exception):
    """Raised when no active integration credentials exist for a tenant and provider."""

    def __init__(self, provider: str):
        super().__init__(f"No active credentials found for provider '{provider}'")
        self.provider = provider


async def validate_meta_token(
    provider: str,
    account_id: str,
    access_token: str,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Validate token with a cheap Graph API call before saving credentials.

    Never logs the access token. Raises AuthError(400) if validation fails.
    """
    version = settings.meta_graph_version or "v21.0"
    url = f"{GRAPH_API_BASE}/{version}/{account_id}"

    # Allow passing an existing client or using a temporary one
    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
        should_close = True

    try:
        resp = await client.get(url, params={"access_token": access_token})
        if resp.status_code >= 400:
            logger.warning(
                "integration.token_validation_failed provider=%s account_id=%s status=%d",
                provider,
                account_id,
                resp.status_code,
            )
            raise AuthError(400, "invalid_credentials", "Invalid integration token or account ID")
    except httpx.RequestError as exc:
        logger.error(
            "integration.validation_network_error provider=%s account_id=%s err=%s",
            provider,
            account_id,
            str(exc),
        )
        raise AuthError(502, "provider_error", "Failed to connect to Meta Graph API") from exc
    finally:
        if should_close:
            await client.aclose()


def connect_integration(
    session: Session,
    context: TenantContext,
    provider: str,
    provider_account_id: str,
    access_token: str,
    waba_id: str | None = None,
    scopes: list[str] | None = None,
) -> Integration:
    """Connect or update integration credentials.

    Credentials are encrypted before insertion and never returned or logged.
    """
    if provider not in {"whatsapp", "meta"}:
        raise AuthError(400, "unsupported_provider", f"Unsupported provider: {provider}")

    # Check if this provider_account_id is already claimed by another tenant
    existing_other = session.execute(
        select(Integration).where(
            Integration.provider == provider,
            Integration.provider_account_id == provider_account_id,
            Integration.tenant_id != context.tenant_id,
        )
    ).scalar_one_or_none()

    if existing_other is not None:
        raise AuthError(
            409,
            "account_already_registered",
            "This external account is already registered to another company",
        )

    # Check if integration already exists for this tenant
    integration = session.execute(
        select(Integration).where(
            Integration.tenant_id == context.tenant_id,
            Integration.provider == provider,
            Integration.provider_account_id == provider_account_id,
        )
    ).scalar_one_or_none()

    if integration is None:
        integration = Integration(
            tenant_id=context.tenant_id,
            provider=provider,
            provider_account_id=provider_account_id,
            owner_user_id=context.user_id,
            scopes=scopes or ["messages", "webhooks"],
            status="active",
            key_version=1,
        )
        session.add(integration)
        session.flush()  # Generate integration.id for AAD binding
    else:
        integration.status = "active"
        integration.owner_user_id = context.user_id
        if scopes:
            integration.scopes = scopes

    # Encrypt credentials dictionary with tenant_id:integration_id as AAD
    credentials_payload = {
        "access_token": access_token,
        "provider_account_id": provider_account_id,
    }
    if waba_id:
        credentials_payload["waba_id"] = waba_id

    integration.credentials_encrypted = encrypt_credentials(
        credentials_payload,
        context.tenant_id,
        integration.id,
        key_version=integration.key_version,
    )

    # Record audit log without sensitive tokens
    record_audit_event(
        session,
        action="integration.connect",
        actor_type="user",
        tenant_id=context.tenant_id,
        actor_user_id=context.user_id,
        entity_type="integration",
        entity_id=integration.id,
        details={
            "provider": provider,
            "provider_account_id": provider_account_id,
            "scopes": integration.scopes,
        },
    )

    session.commit()
    session.refresh(integration)
    return integration


def list_integrations(
    session: Session,
    context: TenantContext,
) -> list[Integration]:
    """List integrations for the current tenant.

    Credentials are never loaded or returned in API responses.
    """
    return list(
        session.execute(
            select(Integration)
            .where(Integration.tenant_id == context.tenant_id)
            .order_by(Integration.created_at.desc())
        ).scalars().all()
    )


def disconnect_integration(
    session: Session,
    context: TenantContext,
    integration_id: uuid.UUID,
) -> Integration:
    """Soft-disconnect an integration by setting status to disabled.

    Preserves composite foreign keys to webhook_events.
    """
    integration = session.execute(
        select(Integration).where(
            Integration.tenant_id == context.tenant_id,
            Integration.id == integration_id,
        )
    ).scalar_one_or_none()

    if integration is None:
        raise AuthError(404, "not_found", "Integration not found")

    integration.status = "disabled"

    record_audit_event(
        session,
        action="integration.disconnect",
        actor_type="user",
        tenant_id=context.tenant_id,
        actor_user_id=context.user_id,
        entity_type="integration",
        entity_id=integration.id,
        details={
            "provider": integration.provider,
            "provider_account_id": integration.provider_account_id,
        },
    )

    session.commit()
    session.refresh(integration)
    return integration


def get_credentials(
    tenant_id: uuid.UUID,
    provider: str,
    session: Session,
) -> dict[str, Any]:
    """Retrieve decrypted credentials for an active integration.

    Falls back to test environment configuration if no database integration
    is configured (development/test stubbing).
    """
    row = session.execute(
        select(Integration).where(
            Integration.tenant_id == tenant_id,
            Integration.provider == provider,
            Integration.status == "active",
        ).limit(1)
    ).scalar_one_or_none()

    if row is not None and row.credentials_encrypted:
        return decrypt_credentials(
            row.credentials_encrypted,
            tenant_id,
            row.id,
        )

    # Stub fallback for local test/dev
    if provider == "whatsapp":
        token = getattr(settings, "whatsapp_access_token", None) or os_env_wa_token()
        phone_id = getattr(settings, "whatsapp_phone_number_id", None) or os_env_wa_phone()
        if token and phone_id:
            return {"access_token": token, "phone_number_id": phone_id}

    raise CredentialsNotFound(provider)


def os_env_wa_token() -> str:
    import os
    return os.environ.get("WHATSAPP_ACCESS_TOKEN", "") or os.environ.get("TEST_WA_TOKEN", "")


def os_env_wa_phone() -> str:
    import os
    return (
        os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        or os.environ.get("TEST_WA_PHONE_NUMBER_ID", "")
    )
