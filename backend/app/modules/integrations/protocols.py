"""Shared webhook contracts — agreed in the Day 7 mob session.

Every webhook provider (WhatsApp, Meta Lead Ads, Messenger) must implement
the WebhookProvider Protocol.  The dispatcher (webhooks.py) calls these
methods in order:

  1. verify_signature()   — before JSON parsing (401 if false)
  2. parse()              — extract ParsedEvent list from the payload
  3. handle()             — business logic, called once per new event

The dispatcher owns tenant resolution and idempotency (record_event).
Providers must NOT resolve the tenant or write to webhook_events themselves.

Signature verification must always go through
app.modules.integrations.signature.verify_signature(); no provider should
contain its own HMAC code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ParsedEvent:
    """A single normalised event extracted from a provider webhook payload.

    account_id  — provider's account identifier used to look up the tenant.
                  WhatsApp: phone_number_id.  Meta/Messenger: page_id.
    event_id    — provider-assigned unique ID used for deduplication.
                  WhatsApp messages: wamid.  Lead Ads: leadgen_id.
                  Messenger: mid.  Status callbacks: "{wamid}:{status}".
    event_type  — one of "message", "status", "leadgen".  Stored in
                  webhook_events.event_type (NOT NULL).
    data        — raw provider payload slice for this event.  May contain PII;
                  never log this field.
    """

    account_id: str
    event_id: str
    event_type: str
    data: dict[str, Any]


@runtime_checkable
class WebhookProvider(Protocol):
    """Protocol that every webhook provider must satisfy.

    Implementors: WhatsAppProvider (Dev 1), MetaProvider (Dev 5).
    The dispatcher (webhooks.py) is the only caller; do not call these
    methods directly from route handlers or business logic.

    name must match the value stored in integrations.provider and the
    URL path segment (e.g. /api/v1/webhooks/whatsapp).
    """

    #: Stored in integrations.provider. Must be lowercase, e.g. "whatsapp".
    name: str

    def verify_challenge(
        self,
        mode: str | None,
        token: str | None,
        challenge: str | None,
    ) -> str:
        """Verify a Meta hub.challenge GET handshake.

        Rules:
        - mode must equal "subscribe".
        - token must equal settings.webhook_verify_token in constant time
          (use hmac.compare_digest — do not use == or 'in').
        - Return the raw challenge string on success (echoed as plain text,
          HTTP 200 by the router).
        - Raise AuthError(403, "forbidden", ...) on any failure.

        Never raise on an empty challenge; return "" so Meta retries.
        """
        ...

    def verify_signature(
        self,
        raw_body: bytes,
        signature_header: str | None,
    ) -> bool:
        """Return True only if the HMAC-SHA256 signature is valid.

        Implementation MUST delegate to:
            app.modules.integrations.signature.verify_signature(
                raw_body, signature_header, secret
            )
        where secret is the Meta app secret from settings.

        Never write HMAC code inside a provider.  Never read the token from
        anywhere other than settings.
        """
        ...

    def parse(self, payload: dict[str, Any]) -> list[ParsedEvent]:
        """Extract ParsedEvent objects from the raw decoded payload.

        - Return an empty list for payloads that contain no actionable events
          (e.g. a delivery receipt batch with no messages).
        - Never raise for unexpected fields; skip unrecognised structures.
        - Status callbacks (sent/delivered/read) should be returned as
          ParsedEvent(event_type="status") so they are deduplicated but are
          not passed to handle().
        """
        ...

    async def handle(
        self,
        event: ParsedEvent,
        session: Session,
        tenant_id: uuid.UUID,
        integration_id: uuid.UUID,
    ) -> None:
        """Process one new, deduplicated event.

        Called by the dispatcher only after:
          - Signature has been verified.
          - Tenant and integration have been resolved.
          - The event has been inserted into webhook_events (record_event
            returned a non-None id — i.e. this is not a duplicate).

        Responsibilities (Dev 1 / Dev 5):
          - Normalise phone numbers to E.164.
          - Call the capture service (find or create lead).
          - Find or create the conversation.
          - Insert the inbound message; update last_inbound_at.
          - Run opt-out handling if the text is a stop keyword.
          - Emit no-op hook ("message.received").

        Rules:
          - Do NOT commit or rollback the session; the dispatcher owns the
            transaction.
          - Do NOT re-resolve the tenant; use the tenant_id argument.
          - Treat a unique-constraint violation on provider_message_id as a
            duplicate and return silently (second line of defence).
          - For "status" event_type, log and return without further action.
        """
        ...

