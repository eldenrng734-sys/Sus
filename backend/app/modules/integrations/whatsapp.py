"""WhatsApp Webhook Provider (Dev 1).

Implements the WebhookProvider protocol for WhatsApp:
  - GET handshake challenge verification (constant-time).
  - Webhook signature verification via Dev 2's signature helper.
  - Event extraction from entry[].changes[].value.
  - Handling inbound messages: E.164 normalization, lead capture,
    conversation find/create, message insert, last_inbound_at update,
    stop-keyword opt-out handling, and no-op message.received event hook.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Message
from app.modules.integrations.inbound import InboundMessage, store_inbound_message
from app.modules.integrations.protocols import AfterCommitJob, ParsedEvent
from app.modules.integrations.registry import register_provider
from app.modules.integrations.signature import verify_signature
from app.modules.leads.capture_normalize import clean_name, normalize_phone

logger = logging.getLogger(__name__)


class WhatsAppProvider:
    """Webhook provider implementation for WhatsApp Business API."""

    name: str = "whatsapp"

    def verify_challenge(
        self,
        mode: str | None,
        token: str | None,
        challenge: str | None,
    ) -> str:
        """Answer Meta's GET verification request.

        Compares the verify token in constant time. Returns the raw hub.challenge.
        """
        expected = (
            settings.webhook_verify_token.get_secret_value()
            or settings.whatsapp_verify_token.get_secret_value()
        )

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
        """Verify Meta X-Hub-Signature-256 header using the shared helper."""
        return verify_signature(
            raw_body,
            signature_header,
            settings.meta_app_secret.get_secret_value(),
        )

    def parse(self, payload: dict[str, Any]) -> list[ParsedEvent]:
        """Parse Meta WhatsApp payload into a list of ParsedEvent instances.

        Reads entry[].changes[].value:
          - metadata.phone_number_id -> account_id
          - contacts[] -> wa_id to contact_name mapping
          - messages[] -> inbound messages
          - statuses[] -> sent/delivered/read/failed delivery receipts
        """
        if not isinstance(payload, dict) or not isinstance(payload.get("entry"), list):
            raise AuthError(400, "malformed_payload", "Payload is not a valid webhook")

        events: list[ParsedEvent] = []

        for entry in payload.get("entry", []):
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes", []):
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue

                metadata = value.get("metadata")
                if not isinstance(metadata, dict):
                    continue

                account_id = str(metadata.get("phone_number_id") or "")
                if not account_id:
                    continue

                contacts_map: dict[str, str] = {}
                for contact in value.get("contacts", []):
                    if isinstance(contact, dict):
                        wa_id = str(contact.get("wa_id") or "")
                        profile = contact.get("profile") or {}
                        name = profile.get("name") if isinstance(profile, dict) else None
                        if wa_id and name:
                            contacts_map[wa_id] = name

                # Messages
                for msg in value.get("messages", []):
                    if not isinstance(msg, dict):
                        continue
                    msg_id = str(msg.get("id") or "")
                    if not msg_id:
                        continue

                    sender = str(msg.get("from") or "")
                    contact_name = contacts_map.get(sender) or sender
                    events.append(
                        ParsedEvent(
                            account_id=account_id,
                            event_id=msg_id,
                            event_type="message",
                            data={
                                "message": msg,
                                "contact_name": contact_name,
                                "phone_number_id": account_id,
                            },
                        )
                    )

                # Status updates (sent/delivered/read/failed)
                for status in value.get("statuses", []):
                    if not isinstance(status, dict):
                        continue
                    status_id = str(status.get("id") or "")
                    state = str(status.get("status") or "")
                    if not status_id:
                        continue

                    event_id = f"{status_id}:{state}" if state else status_id
                    events.append(
                        ParsedEvent(
                            account_id=account_id,
                            event_id=event_id,
                            event_type="status",
                            data={
                                "status": status,
                                "phone_number_id": account_id,
                            },
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
        """Process a deduplicated WhatsApp inbound event."""
        # Set tenant context on DB session for RLS
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )

        if event.event_type == "status":
            # Status events (sent, delivered, read, failed): log and update message if present
            status_data = event.data.get("status", {})
            logger.info(
                "whatsapp_status_received account=%s wamid=%s status=%s",
                event.account_id,
                status_data.get("id"),
                status_data.get("status"),
            )
            wamid = status_data.get("id")
            new_status = status_data.get("status")
            if wamid and new_status in {"sent", "delivered", "read", "failed"}:
                db_msg = session.execute(
                    select(Message)
                    .where(
                        Message.tenant_id == tenant_id,
                        Message.provider == "whatsapp",
                        Message.provider_message_id == wamid,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if db_msg is not None:
                    db_msg.status = new_status
                    now = datetime.now(UTC)
                    if new_status == "delivered":
                        db_msg.delivered_at = now
                    elif new_status == "read":
                        db_msg.read_at = now
                    elif new_status == "failed":
                        errors = status_data.get("errors") or [{}]
                        first_error = errors[0] if isinstance(errors[0], dict) else {}
                        db_msg.error_code = first_error.get("title", "failed")
            return None

        if event.event_type != "message":
            return None

        msg = event.data.get("message", {})
        sender_raw = str(msg.get("from") or "")
        if not sender_raw:
            return None

        # 1. Normalize sender's number to E.164 (+8801...)
        try:
            phone_e164 = normalize_phone(sender_raw)
        except Exception:
            # Fallback if raw digits don't parse standardly
            digits = "".join(filter(str.isdigit, sender_raw))
            phone_e164 = f"+{digits}" if digits else sender_raw

        raw_contact_name = event.data.get("contact_name") or phone_e164
        try:
            contact_name = clean_name(raw_contact_name)
        except Exception:
            contact_name = phone_e164 or "WhatsApp Lead"

        # 2. Extract message text and attachment reference
        msg_type = msg.get("type", "text")
        if msg_type == "text":
            text_payload = msg.get("text")
            body_text = text_payload.get("body", "") if isinstance(text_payload, dict) else ""
            attachment_ref = None
        else:
            body_text = f"[{msg_type}]"
            attachment_data = msg.get(msg_type)
            attachment_ref = (
                attachment_data.get("id") if isinstance(attachment_data, dict) else None
            )

        # 3. Single shared pipeline: capture -> conversation -> message -> opt-out
        store_inbound_message(
            session,
            tenant_id=tenant_id,
            inbound=InboundMessage(
                provider="whatsapp",
                channel="whatsapp",
                source="whatsapp",
                account_id=event.account_id,
                external_contact_id=phone_e164,
                external_conversation_id=phone_e164,
                external_lead_id=phone_e164,
                contact_name=contact_name,
                message_id=event.event_id,
                body_text=body_text,
                attachment_reference=attachment_ref,
                phone=phone_e164,
                consent=True,
                consent_source="whatsapp",
            ),
        )
        return None


# Register default WhatsApp provider instance
whatsapp_provider = WhatsAppProvider()
register_provider(whatsapp_provider)
