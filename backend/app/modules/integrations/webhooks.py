"""Webhook dispatcher framework.

Verify the raw request signature before parsing JSON.
Resolve the tenant exclusively through the registered integration.
Write idempotency records via record_event() — never raw INSERT.

Call order enforced here:
  1. Signature check (401 on failure — before any DB write)
  2. JSON parse (400 on failure)
  3. extract_events() — produce ParsedEvent list
  4. Per event: resolve_integration → record_event → provider.handle()

The dispatcher owns the transaction; providers must not commit or rollback.
Unknown account IDs are silently skipped (HTTP 200) so Meta does not retry.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.errors import AuthError
from app.modules.integrations import whatsapp as _wa_init  # noqa: F401
from app.modules.integrations.models import record_event
from app.modules.integrations.registry import get_provider
from app.modules.integrations.signature import verify_signature

logger = logging.getLogger(__name__)

PROVIDERS = {"whatsapp", "meta"}
MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True)
class ParsedEvent:
    account_id: str
    event_id: str
    event_type: str
    data: dict


def _secret_for(provider: str) -> str:
    # Both WhatsApp and Meta (Lead Ads / Messenger) share the same app secret.
    return settings.meta_app_secret.get_secret_value()


def _dicts(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _fallback_id(obj: dict) -> str:
    raw = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "h-" + hashlib.sha256(raw).hexdigest()


def extract_events(provider: str, payload: Any) -> list[ParsedEvent]:
    if provider not in PROVIDERS:
        raise AuthError(404, "not_found", "Unknown provider")

    if not isinstance(payload, dict) or not isinstance(payload.get("entry"), list):
        raise AuthError(400, "malformed_payload", "Payload is not a valid webhook")

    events: list[ParsedEvent] = []

    for entry in _dicts(payload["entry"]):
        if provider == "whatsapp":
            for change in _dicts(entry.get("changes")):
                value = change.get("value")
                if not isinstance(value, dict):
                    continue

                metadata = value.get("metadata")
                if not isinstance(metadata, dict):
                    continue

                account = str(metadata.get("phone_number_id") or "")
                if not account:
                    continue

                for message in _dicts(value.get("messages")):
                    event_id = str(message.get("id") or _fallback_id(message))
                    events.append(ParsedEvent(account, event_id, "message", message))

                for status in _dicts(value.get("statuses")):
                    message_id = status.get("id")
                    state = status.get("status")

                    event_id = (
                        f"{message_id}:{state}" if message_id and state else _fallback_id(status)
                    )

                    events.append(ParsedEvent(account, event_id, "status", status))

        else:  # meta — Messenger and Lead Ads
            account = str(entry.get("id") or "")
            if not account:
                continue

            for item in _dicts(entry.get("messaging")):
                message = item.get("message")
                if not isinstance(message, dict):
                    message = {}

                event_id = str(message.get("mid") or _fallback_id(item))
                events.append(ParsedEvent(account, event_id, "message", item))

            for change in _dicts(entry.get("changes")):
                value = change.get("value")
                if not isinstance(value, dict):
                    value = {}

                event_id = str(value.get("leadgen_id") or _fallback_id(change))

                events.append(
                    ParsedEvent(
                        account,
                        event_id,
                        str(change.get("field") or "change"),
                        change,
                    )
                )

    return events


def _set_local(session: Session, key: str, value: str) -> None:
    session.execute(
        text("SELECT set_config(:setting_name, :setting_value, true)"),
        {
            "setting_name": key,
            "setting_value": value,
        },
    )


def _resolve_integration(
    session: Session,
    provider: str,
    account_id: str,
) -> tuple[UUID, UUID] | None:
    """Return (tenant_id, integration_id) for one active integration, or None.

    Returns None — not an error — when the account is unknown. Callers must
    return HTTP 200 and skip processing so Meta does not keep retrying.

    Calls the narrow SECURITY DEFINER SQL function resolve_integration(provider, account_id).
    """
    row = session.execute(
        text("SELECT tenant_id, integration_id FROM resolve_integration(:p, :a)"),
        {"p": provider, "a": account_id},
    ).first()

    if row is None:
        logger.warning(
            "webhook.unknown_account provider=%s account_id=%s",
            provider,
            account_id,
        )
        return None

    return row.tenant_id, row.integration_id


async def receive(
    session: Session,
    provider: str,
    raw_body: bytes,
    signature_header: str | None,
) -> dict:
    if provider not in PROVIDERS:
        raise AuthError(404, "not_found", "Unknown provider")

    if len(raw_body) > MAX_BODY_BYTES:
        raise AuthError(
            413,
            "payload_too_large",
            "Webhook body is too large",
        )

    provider_impl = get_provider(provider)

    # Signature verification happens before JSON parsing — always.
    if provider_impl is not None:
        if not provider_impl.verify_signature(raw_body, signature_header):
            raise AuthError(
                401,
                "invalid_signature",
                "Invalid signature",
            )
    else:
        if not verify_signature(
            raw_body,
            signature_header,
            _secret_for(provider),
        ):
            raise AuthError(
                401,
                "invalid_signature",
                "Invalid signature",
            )

    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthError(
            400,
            "malformed_payload",
            "Body is not valid JSON",
        ) from exc

    if provider_impl is not None:
        events = provider_impl.parse(payload)
    else:
        events = extract_events(provider, payload)

    stored = 0
    duplicates = 0
    skipped = 0
    # Cache per-request to avoid one DB round-trip per event from the same account.
    resolved: dict[str, tuple[UUID, UUID] | None] = {}

    try:
        for event in events:
            if event.account_id not in resolved:
                resolved[event.account_id] = _resolve_integration(
                    session,
                    provider,
                    event.account_id,
                )

            result = resolved[event.account_id]
            if result is None:
                # Unknown account — acknowledge but do not process.
                skipped += 1
                continue

            tenant_id, integration_id = result

            # Set tenant context for RLS on any subsequent ORM queries in
            # this transaction (e.g. inside provider.handle()).
            _set_local(session, "app.tenant_id", str(tenant_id))

            # record_event handles idempotency via ON CONFLICT DO NOTHING.
            # None return means the event already exists — skip handle().
            new_id = record_event(
                session,
                tenant_id=tenant_id,
                integration_id=integration_id,
                provider=provider,
                event_id=event.event_id,
                event_type=event.event_type,
                payload=event.data,
            )

            if new_id is None:
                duplicates += 1
            else:
                stored += 1
                if provider_impl is not None:
                    await provider_impl.handle(
                        event,
                        session,
                        tenant_id,
                        integration_id,
                    )

        # Acknowledge only after all events are durable.
        session.commit()

    except Exception:
        session.rollback()
        raise

    return {
        "stored": stored,
        "duplicates": duplicates,
        "skipped": skipped,
    }


def verify_challenge(
    mode: str | None,
    token: str | None,
    challenge: str | None,
    provider: str | None = None,
) -> str:
    if provider:
        p = get_provider(provider)
        if p is not None:
            return p.verify_challenge(mode, token, challenge)

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
