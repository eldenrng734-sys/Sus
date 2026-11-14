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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation, Message
from app.modules.integrations.protocols import ParsedEvent
from app.modules.integrations.registry import register_provider
from app.modules.integrations.signature import verify_signature
from app.modules.leads.capture import CaptureInput, capture_lead
from app.modules.leads.capture_normalize import clean_name, normalize_phone
from app.modules.leads.optout import apply_opt_out, is_opt_out_message

logger = logging.getLogger(__name__)


def emit(event_name: str, payload: dict[str, Any]) -> None:
    """No-op event emitter. Dev 2 builds the real emitter on Day 10."""
    logger.debug("emit_hook event=%s payload=%s", event_name, payload)


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
    ) -> None:
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
                    select(Message).where(
                        Message.tenant_id == tenant_id,
                        Message.provider == "whatsapp",
                        Message.provider_message_id == wamid,
                    ).limit(1)
                ).scalar_one_or_none()
                if db_msg is not None:
                    db_msg.status = new_status
                    now = datetime.now(UTC)
                    if new_status == "delivered":
                        db_msg.delivered_at = now
                    elif new_status == "read":
                        db_msg.read_at = now
                    elif new_status == "failed":
                        db_msg.error_code = status_data.get("errors", [{}])[0].get("title", "failed")
            return

        if event.event_type != "message":
            return

        msg = event.data.get("message", {})
        sender_raw = str(msg.get("from") or "")
        if not sender_raw:
            return

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

        # 2. Call Day 6 capture service (source="whatsapp", external_id=phone_e164)
        capture_input = CaptureInput(
            name=contact_name,
            phone=phone_e164,
            source="whatsapp",
            external_id=phone_e164,
            consent=True,
            consent_source="whatsapp",
        )
        capture_result = capture_lead(
            session,
            tenant_id=tenant_id,
            data=capture_input,
        )
        lead = capture_result.lead

        # 3. Find or create the conversation
        now = datetime.now(UTC)
        conv = session.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.channel == "whatsapp",
                Conversation.lead_id == lead.id,
            ).limit(1)
        ).scalar_one_or_none()

        if conv is None:
            conv = Conversation(
                tenant_id=tenant_id,
                lead_id=lead.id,
                channel="whatsapp",
                external_contact_id=phone_e164,
                external_conversation_id=phone_e164,
                status="open",
                assigned_user_id=lead.assigned_user_id,
                last_inbound_at=now,
                last_message_at=now,
            )
            session.add(conv)
            session.flush()
        else:
            conv.last_inbound_at = now
            conv.last_message_at = now
            if not conv.external_contact_id:
                conv.external_contact_id = phone_e164

        # 4. Extract message text and attachment reference
        msg_type = msg.get("type", "text")
        if msg_type == "text":
            body_text = msg.get("text", {}).get("body", "")
            attachment_ref = None
        else:
            body_text = f"[{msg_type}]"
            attachment_data = msg.get(msg_type)
            attachment_ref = (
                attachment_data.get("id") if isinstance(attachment_data, dict) else None
            )

        # 5. Insert inbound message
        inbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            provider="whatsapp",
            provider_message_id=event.event_id,
            direction="inbound",
            message_text=body_text,
            attachment_reference=attachment_ref,
            status="received",
        )
        session.add(inbound_message)
        try:
            session.flush()
        except IntegrityError:
            # Second line of defense: duplicate provider_message_id is ignored
            session.rollback()
            logger.info(
                "whatsapp_duplicate_message wamid=%s tenant=%s ignored",
                event.event_id,
                tenant_id,
            )
            return

        # 6. Check opt-out stop keywords (including Bangla: 'বন্ধ', 'বন্ধ করুন')
        if body_text and is_opt_out_message(body_text):
            apply_opt_out(session, lead.id, source="whatsapp")

        # 7. Emit no-op message.received hook
        emit(
            "message.received",
            {
                "tenant_id": str(tenant_id),
                "conversation_id": str(conv.id),
                "message_id": str(inbound_message.id),
                "lead_id": str(lead.id),
            },
        )


# Register default WhatsApp provider instance
whatsapp_provider = WhatsAppProvider()
register_provider(whatsapp_provider)

