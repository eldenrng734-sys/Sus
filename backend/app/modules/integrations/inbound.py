"""Shared inbound-chat storage for WhatsApp and Messenger.

Both providers receive the same shape of data after their own payload parsing:
a sender, a message id, optional text and attachments. This module performs the
single pipeline the project requires:

    capture_lead() -> find/create conversation -> insert inbound message
    -> opt-out handling -> message.received hook

The caller must already have set the verified tenant context. The webhook
dispatcher owns the transaction and sweeps pending changes; this module never
calls ``commit()`` (except through the existing opt-out service, which is a
deliberate business action).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.outbox import emit_message_received
from app.modules.conversations.models import Conversation, Message
from app.modules.leads.capture import CaptureInput, CaptureResult, capture_lead
from app.modules.leads.capture_normalize import (
    extract_message_email,
    extract_message_phone,
)
from app.modules.leads.optout import apply_opt_out, is_opt_out_message

logger = logging.getLogger(__name__)


def emit(event_name: str, payload: dict[str, Any]) -> None:
    """No-op event emitter. Dev 2 builds the real emitter on Day 10."""
    logger.debug("emit_hook event=%s payload=%s", event_name, payload)


@dataclass(frozen=True)
class InboundMessage:
    """Normalised message produced by a provider's ``handle()``."""

    provider: str  # stored in messages.provider: whatsapp | messenger
    channel: str  # stored in conversations.channel
    source: str  # stored in leads.source
    account_id: str
    external_contact_id: str
    external_conversation_id: str
    external_lead_id: str
    contact_name: str
    message_id: str
    body_text: str
    attachment_reference: str | None = None
    phone: str | None = None
    email: str | None = None
    consent: bool = False
    consent_source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InboundResult:
    capture: CaptureResult
    conversation: Conversation
    message: Message | None  # None when the provider message id already existed


def store_inbound_message(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    inbound: InboundMessage,
) -> InboundResult:
    """Store one inbound message using the shared lead-capture pipeline."""
    phone = inbound.phone or extract_message_phone(inbound.body_text)
    email = inbound.email or extract_message_email(inbound.body_text)

    capture = capture_lead(
        session,
        tenant_id=tenant_id,
        data=CaptureInput(
            name=inbound.contact_name,
            phone=phone,
            email=email,
            source=inbound.source,
            external_id=inbound.external_lead_id,
            consent=inbound.consent,
            consent_source=inbound.consent_source,
            interaction_metadata={
                "account_id": inbound.account_id,
                "provider_message_id": inbound.message_id,
                **inbound.metadata,
            },
        ),
    )
    lead = capture.lead

    now = datetime.now(UTC)
    conversation = session.execute(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == inbound.channel,
            Conversation.lead_id == lead.id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant_id,
            lead_id=lead.id,
            channel=inbound.channel,
            external_contact_id=inbound.external_contact_id,
            external_conversation_id=inbound.external_conversation_id,
            status="open",
            assigned_user_id=lead.assigned_user_id,
            last_inbound_at=now,
            last_message_at=now,
        )
        session.add(conversation)
        session.flush()
    else:
        conversation.last_inbound_at = now
        conversation.last_message_at = now
        if not conversation.external_contact_id:
            conversation.external_contact_id = inbound.external_contact_id
        if not conversation.external_conversation_id:
            conversation.external_conversation_id = inbound.external_conversation_id

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        provider=inbound.provider,
        provider_message_id=inbound.message_id,
        direction="inbound",
        message_text=inbound.body_text,
        attachment_reference=inbound.attachment_reference,
        status="received",
    )

    # Second line of defence. Use a savepoint so a duplicate cannot erase the
    # lead/conversation changes that capture_lead just flushed.
    try:
        with session.begin_nested():
            session.add(message)
            session.flush()
    except IntegrityError:
        logger.info(
            "inbound_duplicate_message provider=%s provider_message_id=%s ignored",
            inbound.provider,
            inbound.message_id,
        )
        return InboundResult(capture=capture, conversation=conversation, message=None)

    if inbound.body_text and is_opt_out_message(inbound.body_text):
        apply_opt_out(session, lead.id, source=inbound.source)
    else:
        from app.modules.tasks.service import pause_followups

        pause_followups(session, lead.id, reason="customer_reply")

    emit_message_received(
        session,
        tenant_id=tenant_id,
        message_id=message.id,
        conversation_id=conversation.id,
    )

    return InboundResult(capture=capture, conversation=conversation, message=message)
