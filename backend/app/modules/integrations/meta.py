"""Meta Page provider: Lead Ads and Messenger (test mode).

Implements ``WebhookProvider`` for the single Meta app webhook endpoint
``/api/v1/webhooks/meta``:

  - GET handshake verification (constant time).
  - X-Hub-Signature-256 verification through the shared helper.
  - ``entry[].changes[field=leadgen]`` -> leadgen event.
  - ``entry[].messaging[]`` -> inbound Messenger message (echoes, delivery and
    read receipts are ignored).

Lead Ads payloads only contain an ID, so an after-commit background job fetches
the field data from Graph API. The webhook is acknowledged as soon as the
receipt is durable; we never make Meta wait for the detail fetch.

Security notes:
  - Page access tokens live only in memory and are never logged or put in URLs.
  - Lead field data is PII: never log it.
  - The page id in ``entry[].id`` is resolved to a tenant by the dispatcher; we
    never trust tenant or lead identifiers from the payload.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import set_tenant_context
from app.modules.auth.errors import AuthError
from app.modules.integrations.inbound import InboundMessage, store_inbound_message
from app.modules.integrations.models import (
    mark_webhook_event_failed,
    mark_webhook_event_processed,
)
from app.modules.integrations.protocols import AfterCommitJob, ParsedEvent
from app.modules.integrations.registry import register_provider
from app.modules.integrations.service import CredentialsNotFound, get_credentials
from app.modules.integrations.signature import verify_signature
from app.modules.leads.capture import CaptureError, CaptureInput, capture_lead

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"

# Permissions the Meta app must be granted before this integration can work:
#   leads_retrieval, ads_management, pages_manage_metadata
# They are requested during app review / OAuth, not at webhook time.
SUBSCRIBED_FIELDS = "leadgen,messages,messaging_postbacks"
REQUIRED_SCOPES = frozenset({"leads_retrieval", "ads_management", "pages_manage_metadata"})

LEAD_FETCH_FIELDS = "field_data,ad_id,form_id"
MAX_SAFE_ERROR_LENGTH = 200


class MetaGraphError(Exception):
    """A Graph API call failed. The message never contains a token or PII."""

    def __init__(self, status_code: int | None, error_code: str | None = None) -> None:
        self.status_code = status_code
        self.error_code = error_code or "unknown"
        super().__init__(f"Meta Graph API request failed ({status_code}:{self.error_code})")

    def safe_label(self) -> str:
        if self.status_code is None:
            return "graph_network_error"
        return f"graph_{self.status_code}:{self.error_code}"[:MAX_SAFE_ERROR_LENGTH]


def _provider_error_code(response: httpx.Response) -> str:
    """Return a short, non-PII provider error label for storage/debugging."""
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return f"http_{response.status_code}"

    if not isinstance(error, dict):
        return f"http_{response.status_code}"

    parts = [
        str(error[key])
        for key in ("code", "error_subcode")
        if isinstance(error.get(key), (int, str)) and str(error[key])
    ]
    return ":".join(parts) or f"http_{response.status_code}"


def _safe_error(exc: Exception) -> str:
    """Convert an exception into a short label safe to persist.

    Raw provider responses, request URLs, and exception messages can contain
    access tokens or customer data, so they are deliberately not stored.
    """
    if isinstance(exc, MetaGraphError):
        return exc.safe_label()
    if isinstance(exc, CaptureError):
        return "capture_rejected"
    if isinstance(exc, httpx.RequestError):
        return "graph_network_error"
    return type(exc).__name__[:MAX_SAFE_ERROR_LENGTH]


def _fallback_id(obj: dict[str, Any]) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "h-" + hashlib.sha256(raw).hexdigest()


def _graph_url(path: str) -> str:
    version = settings.meta_graph_version or "v21.0"
    return f"{GRAPH_API_BASE}/{version}/{path}"


async def subscribe_page(
    page_id: str,
    page_token: str,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Subscribe this app to leadgen/messages/postbacks for one Page.

    Idempotent: Meta replaces the existing subscription. The token is sent in
    the Authorization header so it cannot appear in proxy/access logs.
    """
    if not page_id.isdigit():
        raise AuthError(400, "validation_error", "Meta page id must be numeric")
    if not page_token:
        raise AuthError(400, "validation_error", "A Meta page access token is required")

    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.meta_graph_timeout_seconds)

    try:
        try:
            response = await client.post(
                _graph_url(f"{page_id}/subscribed_apps"),
                data={"subscribed_fields": SUBSCRIBED_FIELDS},
                headers={"Authorization": f"Bearer {page_token}"},
            )
        except httpx.RequestError as exc:
            raise AuthError(
                502,
                "provider_error",
                "Could not reach Meta to subscribe the page",
            ) from exc
    finally:
        if should_close:
            await client.aclose()

    if response.status_code >= 400:
        logger.warning(
            "meta_page_subscription_failed page_id=%s status=%s",
            page_id,
            response.status_code,
        )
        raise AuthError(502, "provider_error", "Meta rejected the page subscription")

    try:
        body = response.json()
    except ValueError:
        body = {}

    if isinstance(body, dict) and body.get("success") is False:
        logger.warning("meta_page_subscription_rejected page_id=%s", page_id)
        raise AuthError(502, "provider_error", "Meta rejected the page subscription")


async def fetch_lead(
    leadgen_id: str,
    page_token: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch one Lead Ad submission from Graph API.

    Only the fields we need are requested. The caller must not log the result:
    it contains the lead's name, email and phone number.
    """
    if not leadgen_id.isdigit():
        raise MetaGraphError(400, "invalid_leadgen_id")

    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.meta_graph_timeout_seconds)

    try:
        try:
            response = await client.get(
                _graph_url(leadgen_id),
                params={"fields": LEAD_FETCH_FIELDS},
                headers={"Authorization": f"Bearer {page_token}"},
            )
        except httpx.RequestError as exc:
            raise MetaGraphError(None, "network_error") from exc
    finally:
        if should_close:
            await client.aclose()

    if response.status_code >= 400:
        logger.warning(
            "meta_lead_fetch_rejected leadgen_id=%s status=%s",
            leadgen_id,
            response.status_code,
        )
        raise MetaGraphError(response.status_code, _provider_error_code(response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaGraphError(response.status_code, "invalid_response") from exc

    if not isinstance(payload, dict):
        raise MetaGraphError(response.status_code, "invalid_response")
    return payload


def extract_lead_fields(payload: dict[str, Any]) -> dict[str, str]:
    """Flatten ``field_data`` to ``{name: first_value}`` and keep unknown fields."""
    fields: dict[str, str] = {}
    raw_fields = payload.get("field_data")
    if not isinstance(raw_fields, list):
        return fields

    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        values = item.get("values")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(values, list) or not values:
            continue
        fields[name.strip()] = str(values[0])
    return fields


@contextmanager
def _session_for(
    bind: Engine | Connection,
    tenant_id: uuid.UUID,
) -> Iterator[Session]:
    """Open an independent session for a post-commit job with RLS context set."""
    if isinstance(bind, Connection):
        bind = bind.engine
    with Session(bind=bind) as session:
        set_tenant_context(session, str(tenant_id))
        yield session


def _failure_job(
    webhook_event_id: uuid.UUID,
    reason: str,
    tenant_id: uuid.UUID,
    bind: Engine | Connection,
) -> AfterCommitJob:
    """Build an after-commit job that records a safe failure label."""

    async def _mark_failed() -> None:
        try:
            with _session_for(bind, tenant_id) as session:
                mark_webhook_event_failed(webhook_event_id, reason, session)
                session.commit()
        except Exception:
            logger.exception(
                "meta_webhook_event_failure_update_failed event_id=%s",
                webhook_event_id,
            )

    return _mark_failed


async def fetch_lead_background(
    leadgen_id: str,
    page_token: str,
    webhook_event_id: uuid.UUID,
    tenant_id: uuid.UUID,
    bind: Engine | Connection,
) -> None:
    """Fetch Lead Ad details after the webhook receipt committed.

    Runs outside the request transaction with its own session and restores the
    transaction-local tenant context before touching tenant tables.
    """
    try:
        payload = await fetch_lead(leadgen_id, page_token)
        fields = extract_lead_fields(payload)

        name = (fields.get("full_name") or "").strip() or f"Facebook lead {leadgen_id}"
        ad_id = payload.get("ad_id")
        form_id = payload.get("form_id")
        campaign = str(ad_id or form_id or "").strip() or None

        with _session_for(bind, tenant_id) as session:
            capture_lead(
                session,
                tenant_id=tenant_id,
                data=CaptureInput(
                    name=name,
                    email=fields.get("email"),
                    phone=fields.get("phone_number"),
                    source="facebook_lead_ads",
                    source_campaign=campaign,
                    external_id=leadgen_id,
                    # Consent is explicit business state. A form submission is
                    # not consent for unrelated follow-ups; Day 6 rules decide.
                    consent=False,
                    interaction_metadata={
                        "leadgen_id": leadgen_id,
                        "ad_id": ad_id,
                        "form_id": form_id,
                        "fields": fields,
                    },
                ),
            )
            mark_webhook_event_processed(webhook_event_id, session)
            session.commit()

        logger.info(
            "meta_lead_captured leadgen_id=%s tenant_id=%s",
            leadgen_id,
            tenant_id,
        )
    except Exception as exc:
        label = _safe_error(exc)
        logger.warning(
            "meta_lead_fetch_failed leadgen_id=%s error=%s",
            leadgen_id,
            label,
        )
        try:
            with _session_for(bind, tenant_id) as session:
                mark_webhook_event_failed(webhook_event_id, label, session)
                session.commit()
        except Exception:
            logger.exception(
                "meta_webhook_event_failure_update_failed event_id=%s",
                webhook_event_id,
            )


class MetaProvider:
    """Webhook provider for Meta Lead Ads and Messenger."""

    name: str = "meta"

    def verify_challenge(
        self,
        mode: str | None,
        token: str | None,
        challenge: str | None,
    ) -> str:
        expected = settings.webhook_verify_token.get_secret_value()

        if (
            mode == "subscribe"
            and expected
            and hmac.compare_digest(
                (token or "").encode("utf-8"),
                expected.encode("utf-8"),
            )
        ):
            return challenge or ""

        raise AuthError(403, "forbidden", "Verification failed")

    def verify_signature(
        self,
        raw_body: bytes,
        signature_header: str | None,
    ) -> bool:
        return verify_signature(
            raw_body,
            signature_header,
            settings.meta_app_secret.get_secret_value(),
        )

    def parse(self, payload: dict[str, Any]) -> list[ParsedEvent]:
        if not isinstance(payload, dict) or not isinstance(payload.get("entry"), list):
            raise AuthError(400, "malformed_payload", "Payload is not a valid webhook")

        # A Page webhook never carries WhatsApp or Instagram objects. Reject a
        # misrouted payload instead of creating leads from the wrong namespace.
        if payload.get("object") not in (None, "page"):
            raise AuthError(400, "malformed_payload", "Payload is not a Page webhook")

        events: list[ParsedEvent] = []

        for entry in payload.get("entry", []):
            if not isinstance(entry, dict):
                continue

            page_id = str(entry.get("id") or "")
            if not page_id:
                continue

            # Lead Ads: entry[].changes[field=leadgen]
            for change in entry.get("changes", []):
                if not isinstance(change, dict) or change.get("field") != "leadgen":
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                leadgen_id = str(value.get("leadgen_id") or "")
                if not leadgen_id:
                    continue
                events.append(
                    ParsedEvent(
                        account_id=page_id,
                        event_id=leadgen_id,
                        event_type="leadgen",
                        data={"leadgen_id": leadgen_id, "page_id": page_id},
                    )
                )

            # Messenger: entry[].messaging[]
            for item in entry.get("messaging", []):
                if not isinstance(item, dict):
                    continue

                sender = item.get("sender")
                sender_id = (
                    str(sender.get("id") or "") if isinstance(sender, dict) else ""
                )
                if sender_id and sender_id == page_id:
                    continue  # page echo of our own outbound message

                if "delivery" in item or "read" in item:
                    continue  # receipts are not messages

                message = item.get("message")
                if not isinstance(message, dict):
                    continue
                if message.get("is_echo") is True:
                    continue

                event_id = str(message.get("mid") or _fallback_id(item))
                events.append(
                    ParsedEvent(
                        account_id=page_id,
                        event_id=event_id,
                        event_type="message",
                        data={"messaging": item},
                    )
                )

        return events

    async def handle(
        self,
        event: ParsedEvent,
        session: Session,
        tenant_id: uuid.UUID,
        integration_id: uuid.UUID,
        webhook_event_id: uuid.UUID,
    ) -> list[AfterCommitJob] | None:
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )

        if event.event_type == "leadgen":
            leadgen_id = str(event.data.get("leadgen_id") or "")
            bind = session.get_bind()

            if not leadgen_id:
                return [
                    _failure_job(
                        webhook_event_id,
                        "missing_leadgen_id",
                        tenant_id,
                        bind,
                    )
                ]

            try:
                credentials = get_credentials(
                    tenant_id,
                    "meta",
                    session,
                    integration_id=integration_id,
                )
            except CredentialsNotFound:
                logger.warning(
                    "meta_lead_credentials_missing tenant_id=%s integration_id=%s",
                    tenant_id,
                    integration_id,
                )
                return [
                    _failure_job(
                        webhook_event_id,
                        "credentials_not_found",
                        tenant_id,
                        bind,
                    )
                ]

            page_token = str(credentials.get("access_token") or "")
            if not page_token:
                return [
                    _failure_job(
                        webhook_event_id,
                        "access_token_missing",
                        tenant_id,
                        bind,
                    )
                ]

            # A closure captures the token in memory only; it is never stored
            # back into webhook_events.payload.
            return [
                partial(
                    fetch_lead_background,
                    leadgen_id=leadgen_id,
                    page_token=page_token,
                    webhook_event_id=webhook_event_id,
                    tenant_id=tenant_id,
                    bind=bind,
                )
            ]

        if event.event_type != "message":
            return None

        messaging = event.data.get("messaging")
        if not isinstance(messaging, dict):
            return None

        sender = messaging.get("sender")
        sender_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
        if not sender_id or sender_id == event.account_id:
            return None

        message = messaging.get("message")
        if not isinstance(message, dict) or message.get("is_echo") is True:
            return None

        # Messenger sends ``text`` as a plain string. Accept the WhatsApp-style
        # ``{"body": ...}`` shape too so a shared payload parser keeps working.
        text_payload = message.get("text")
        if isinstance(text_payload, str):
            body_text = text_payload
        elif isinstance(text_payload, dict):
            body_text = str(text_payload.get("body") or "")
        else:
            body_text = ""

        attachments = message.get("attachments")
        attachment_reference: str | None = None
        if isinstance(attachments, list) and attachments:
            first = attachments[0] if isinstance(attachments[0], dict) else {}
            attachment_type = str(first.get("type") or "attachment")
            if not body_text:
                body_text = f"[{attachment_type}]"
            payload = first.get("payload")
            if isinstance(payload, dict) and payload.get("url"):
                attachment_reference = str(payload["url"])

        # PSIDs are page-scoped. Namespacing both IDs by page prevents two
        # Pages of the same tenant from merging unrelated conversations.
        store_inbound_message(
            session,
            tenant_id=tenant_id,
            inbound=InboundMessage(
                provider="messenger",
                channel="messenger",
                source="messenger",
                account_id=event.account_id,
                external_contact_id=sender_id,
                external_conversation_id=f"{event.account_id}:{sender_id}",
                external_lead_id=f"messenger:{event.account_id}:{sender_id}",
                contact_name=f"Messenger contact {sender_id}",
                message_id=str(message.get("mid") or event.event_id),
                body_text=body_text,
                attachment_reference=attachment_reference,
                # A chat message is not a marketing consent. Messenger sending
                # is out of scope today, so leave consent for an explicit flow.
                consent=False,
                consent_source=None,
                metadata={"page_id": event.account_id},
            ),
        )
        return None


meta_provider = MetaProvider()
register_provider(meta_provider)
