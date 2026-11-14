"""Webhook framework.

Verify the raw request signature before parsing JSON.
Resolve the tenant exclusively through the registered integration.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.errors import AuthError
from app.modules.integrations.models import Integration, WebhookEvent
from app.modules.integrations.signature import verify_signature

PROVIDERS = {"whatsapp", "meta"}
MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True)
class ParsedEvent:
    account_id: str
    event_id: str
    event_type: str
    data: dict


def _secret_for(provider: str) -> str:
    if provider == "whatsapp":
        return settings.whatsapp_app_secret
    if provider == "meta":
        return settings.meta_app_secret
    return ""


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

        else:
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


def _resolve_tenant(
    session: Session,
    provider: str,
    account_id: str,
):
    """Resolve exactly one active integration before tenant context exists."""

    _set_local(session, "app.webhook_provider", provider)
    _set_local(session, "app.webhook_account_id", account_id)

    rows = session.execute(
        select(Integration.id, Integration.tenant_id)
        .where(
            Integration.provider == provider,
            Integration.provider_account_id == account_id,
            Integration.status == "active",
            or_(
                Integration.expires_at.is_(None),
                Integration.expires_at > func.now(),
            ),
        )
        .limit(2)
    ).all()

    # Fail closed if no account exists or the account is ambiguous.
    if len(rows) != 1:
        raise AuthError(
            403,
            "unknown_provider_account",
            "Unknown provider account",
        )

    return rows[0].tenant_id


def receive(
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

    # IMPORTANT: argument order matches signature.py.
    # Signature verification happens before JSON parsing.
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

    events = extract_events(provider, payload)

    stored = 0
    duplicates = 0
    tenants: dict[str, Any] = {}

    try:
        for event in events:
            if event.account_id not in tenants:
                tenants[event.account_id] = _resolve_tenant(
                    session,
                    provider,
                    event.account_id,
                )

            tenant_id = tenants[event.account_id]

            # Tenant comes only from the verified integration record.
            _set_local(session, "app.tenant_id", str(tenant_id))

            inserted = session.scalar(
                pg_insert(WebhookEvent)
                .values(
                    tenant_id=tenant_id,
                    provider=provider,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=event.data,
                    signature_valid=True,
                    status="received",
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "tenant_id",
                        "provider",
                        "event_id",
                    ]
                )
                .returning(WebhookEvent.id)
            )

            if inserted is None:
                duplicates += 1
            else:
                stored += 1

        # Acknowledge only after the events are durable.
        session.commit()

    except Exception:
        session.rollback()
        raise

    return {
        "stored": stored,
        "duplicates": duplicates,
    }


def verify_challenge(
    mode: str | None,
    token: str | None,
    challenge: str | None,
) -> str:
    expected = settings.webhook_verify_token

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
