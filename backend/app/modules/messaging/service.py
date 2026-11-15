"""WhatsApp outbound delivery.

The ordering here is a security rule, not a style choice:

1. Authorise the caller against the conversation's lead (same tenant only).
2. Replay an existing idempotent message, or enforce opt-out.
3. Enforce the 24-hour reply window unless an approved template was supplied.
4. Persist the message as ``queued`` and commit.
5. Close the DB transaction and call Meta (never hold a row lock across HTTP).
6. Open a fresh session and move the row to ``sent`` or ``failed``.

Provider payloads and recipient numbers are PII: they are never logged.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tenancy import TenantContext
from app.database.session import set_tenant_context
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation, Message
from app.modules.conversations.schemas import MessageOut
from app.modules.integrations.service import CredentialsNotFound, get_credentials
from app.modules.leads.models import Lead
from app.modules.messaging.graph_client import GraphAPIError, GraphClient, RetryableError
from app.modules.messaging.schemas import MessageSendRequest, TemplatePayload

logger = logging.getLogger(__name__)

WHATSAPP_REPLY_WINDOW = timedelta(hours=24)
MAX_ERROR_CODE_LENGTH = 500


def can_access_lead(context: TenantContext, lead: Lead) -> bool:
    """Mirror ``apply_data_scope`` for a single lead without leaking other tenants."""
    if context.role == "admin":
        return True
    if context.role == "manager":
        return lead.team_id is not None and lead.team_id == context.team_id
    if context.role == "rep":
        return lead.assigned_user_id == context.user_id
    return False


def ensure_lead_authorized(context: TenantContext, lead: Lead) -> None:
    if not can_access_lead(context, lead):
        raise AuthError(403, "forbidden", "You do not have access to this conversation")


def ensure_not_opted_out(lead: Lead) -> None:
    if lead.opted_out:
        raise AuthError(403, "opted_out", "This lead has opted out of messages")


def ensure_whatsapp_conversation(conversation: Conversation) -> None:
    if conversation.channel != "whatsapp":
        raise AuthError(
            422,
            "validation_error",
            "Outbound sending is only supported on WhatsApp conversations",
        )


def ensure_e164_phone(lead: Lead) -> str:
    phone = (lead.phone or "").strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        raise AuthError(
            422,
            "validation_error",
            "The lead phone number must be in E.164 format with a leading '+'",
        )
    return phone


def ensure_window_open(conversation: Conversation, now: datetime | None = None) -> None:
    """A free-form reply is only allowed within 24h of the customer's last message."""
    now = now or datetime.now(UTC)
    cutoff = now - WHATSAPP_REPLY_WINDOW
    if conversation.last_inbound_at is None or conversation.last_inbound_at <= cutoff:
        raise AuthError(
            409,
            "window_closed",
            "The 24-hour WhatsApp reply window is closed. Send an approved template instead.",
        )


def build_text_payload(text: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "text",
        "text": {"body": text},
    }


def build_template_payload(
    name: str,
    language: str,
    params: list[str] | None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "name": name,
        "language": {"code": language},
    }
    if params:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(param)} for param in params],
            }
        ]
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "template",
        "template": template,
    }


def _load_conversation_and_lead(
    session: Session,
    conversation_id: uuid.UUID,
    context: TenantContext | None,
) -> tuple[Conversation, Lead]:
    statement = (
        select(Conversation, Lead)
        .join(
            Lead,
            and_(
                Lead.tenant_id == Conversation.tenant_id,
                Lead.id == Conversation.lead_id,
            ),
        )
        .where(Conversation.id == conversation_id)
    )
    if context is not None:
        # Explicit tenant filter plus RLS; a guessed UUID must never cross tenants.
        statement = statement.where(Conversation.tenant_id == context.tenant_id)

    row = session.execute(statement).first()
    if row is None:
        raise AuthError(404, "not_found", "Conversation not found")
    return row[0], row[1]


def _find_idempotent_message(
    session: Session,
    tenant_id: uuid.UUID,
    idempotency_key: str,
) -> Message | None:
    return session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.idempotency_key == idempotency_key,
        )
        .limit(1)
    )


def _replay_or_conflict(existing: Message, conversation_id: uuid.UUID) -> MessageOut:
    if existing.conversation_id != conversation_id:
        raise AuthError(
            409,
            "idempotency_conflict",
            "This Idempotency-Key was already used for a different conversation",
        )
    return MessageOut.model_validate(existing)


def _resolve_credentials(session: Session, tenant_id: uuid.UUID) -> tuple[str, str]:
    try:
        credentials = get_credentials(tenant_id, "whatsapp", session)
    except CredentialsNotFound as exc:
        raise AuthError(
            503,
            "provider_not_configured",
            "WhatsApp is not connected for this company",
        ) from exc

    token = credentials.get("access_token")
    phone_number_id = credentials.get("phone_number_id") or credentials.get("provider_account_id")
    if not token or not phone_number_id:
        raise AuthError(
            503,
            "provider_not_configured",
            "WhatsApp credentials are incomplete",
        )
    return str(token), str(phone_number_id)


def _queue_message(
    session: Session,
    *,
    conversation: Conversation,
    text: str | None,
    idempotency_key: str | None,
) -> tuple[MessageOut, bool]:
    """Persist the outbound intent as queued. Returns (message, is_replay)."""
    # Capture IDs now: a rollback expires ORM attributes, and reloading them
    # would need the transaction-local RLS context that the rollback just cleared.
    tenant_id = conversation.tenant_id
    conversation_id = conversation.id
    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        provider="whatsapp",
        direction="outbound",
        message_text=text,
        status="queued",
        idempotency_key=idempotency_key,
    )
    session.add(message)
    conversation.last_message_at = datetime.now(UTC)

    try:
        session.flush()
        session.refresh(message)
        queued = MessageOut.model_validate(message)  # copy before commit expires attrs
        session.commit()
        return queued, False
    except IntegrityError as exc:
        session.rollback()
        if idempotency_key:
            # A rollback clears transaction-local RLS state, so restore it before
            # looking up the row that won the concurrent insert race.
            set_tenant_context(session, str(tenant_id))
            existing = _find_idempotent_message(
                session,
                tenant_id,
                idempotency_key,
            )
            if existing is not None:
                return _replay_or_conflict(existing, conversation_id), True
        raise AuthError(409, "conflict", "Could not queue the message") from exc
    except Exception:
        session.rollback()
        raise


def _status_session(bind: Engine | Connection, tenant_id: uuid.UUID) -> Session:
    """Open a fresh session for the post-HTTP status update."""
    if isinstance(bind, Connection):
        bind = bind.engine
    session = Session(bind=bind)
    set_tenant_context(session, str(tenant_id))
    return session


def _finish_sent(
    bind: Engine | Connection,
    tenant_id: uuid.UUID,
    message_id: uuid.UUID,
    provider_message_id: str,
) -> MessageOut:
    with _status_session(bind, tenant_id) as session:
        message = session.scalar(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
            )
        )
        if message is None:
            raise AuthError(500, "internal_error", "Queued message disappeared before delivery")

        message.status = "sent"
        message.provider_message_id = provider_message_id
        message.sent_at = datetime.now(UTC)
        message.error_code = None
        result = MessageOut.model_validate(message)
        session.commit()
        return result


def _finish_failed(
    bind: Engine | Connection,
    tenant_id: uuid.UUID,
    message_id: uuid.UUID,
    error_code: str,
) -> MessageOut:
    with _status_session(bind, tenant_id) as session:
        message = session.scalar(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
            )
        )
        if message is None:
            raise AuthError(500, "internal_error", "Queued message disappeared before delivery")

        message.status = "failed"
        message.error_code = error_code[:MAX_ERROR_CODE_LENGTH]
        result = MessageOut.model_validate(message)
        session.commit()
        return result


async def _send_to_provider(
    *,
    token: str,
    phone_number_id: str,
    to: str,
    payload: dict[str, Any],
) -> str:
    """Call Meta with bounded retries. Permanent 4xx errors are never retried."""
    attempts = max(1, settings.meta_send_max_attempts)

    async with GraphClient(token, phone_number_id) as client:
        for attempt in range(1, attempts + 1):
            try:
                return await client.send_message(to, payload)
            except RetryableError as exc:
                if attempt >= attempts:
                    raise
                delay = max(0.0, settings.meta_send_backoff_seconds) * (2 ** (attempt - 1))
                logger.warning(
                    "whatsapp_send_retry attempt=%d status=%s",
                    attempt,
                    exc.status_code,
                )
                if delay:
                    await asyncio.sleep(delay)

    raise AssertionError("unreachable")  # pragma: no cover


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, GraphAPIError):
        return f"provider_{exc.status_code}:{exc.error_code}"
    if isinstance(exc, RetryableError):
        return (
            f"provider_{exc.status_code}"
            if exc.status_code is not None
            else "provider_network_error"
        )
    return type(exc).__name__


async def _deliver(
    *,
    bind: Engine | Connection,
    tenant_id: uuid.UUID,
    message_id: uuid.UUID,
    to: str,
    payload: dict[str, Any],
    token: str,
    phone_number_id: str,
) -> MessageOut:
    try:
        provider_message_id = await _send_to_provider(
            token=token,
            phone_number_id=phone_number_id,
            to=to,
            payload=payload,
        )
    except (RetryableError, GraphAPIError) as exc:
        logger.warning(
            "whatsapp_send_failed message_id=%s error=%s",
            message_id,
            _failure_code(exc),
        )
        _finish_failed(bind, tenant_id, message_id, _failure_code(exc))
        raise AuthError(
            502,
            "provider_error",
            "WhatsApp did not accept the message. It was saved with status 'failed'.",
            details=[{"message_id": str(message_id), "status": "failed"}],
        ) from exc

    return _finish_sent(bind, tenant_id, message_id, provider_message_id)


async def _persist_and_send(
    *,
    session: Session,
    conversation: Conversation,
    lead: Lead,
    text: str | None,
    payload: dict[str, Any],
    idempotency_key: str | None,
    token: str,
    phone_number_id: str,
) -> tuple[MessageOut, bool]:
    tenant_id = conversation.tenant_id
    to = ensure_e164_phone(lead)
    bind = session.get_bind()

    queued, replay = _queue_message(
        session,
        conversation=conversation,
        text=text,
        idempotency_key=idempotency_key,
    )
    if replay:
        return queued, True

    # Step 4 is committed. Release the request session before the network call.
    session.close()

    sent = await _deliver(
        bind=bind,
        tenant_id=tenant_id,
        message_id=queued.id,
        to=to,
        payload=payload,
        token=token,
        phone_number_id=phone_number_id,
    )
    return sent, False


async def send_message(
    session: Session,
    context: TenantContext,
    body: MessageSendRequest,
    *,
    idempotency_key: str | None = None,
) -> tuple[MessageOut, bool]:
    """Send a rep-authored text or template. Returns (message, is_replay)."""
    conversation, lead = _load_conversation_and_lead(
        session,
        body.conversation_id,
        context,
    )

    # Strict order: authorisation, then idempotent replay, then opt-out/window.
    ensure_lead_authorized(context, lead)

    if idempotency_key:
        existing = _find_idempotent_message(session, conversation.tenant_id, idempotency_key)
        if existing is not None:
            return _replay_or_conflict(existing, conversation.id), True

    ensure_not_opted_out(lead)
    ensure_whatsapp_conversation(conversation)

    if body.template is None:
        ensure_window_open(conversation)

    token, phone_number_id = _resolve_credentials(session, conversation.tenant_id)

    if body.template is not None:
        payload = build_template_payload(
            body.template.name,
            body.template.language,
            body.template.params,
        )
    else:
        payload = build_text_payload(body.text or "")

    return await _persist_and_send(
        session=session,
        conversation=conversation,
        lead=lead,
        text=body.text,
        payload=payload,
        idempotency_key=idempotency_key,
        token=token,
        phone_number_id=phone_number_id,
    )


async def send_template(
    conversation_id: uuid.UUID,
    name: str,
    language: str,
    params: list[str] | None,
    session: Session,
    *,
    idempotency_key: str | None = None,
) -> MessageOut:
    """Send an approved template without going through HTTP.

    Workflow B (n8n) calls this directly. The caller must already have set the
    verified tenant context on ``session``; RLS hides conversations otherwise.
    The 24-hour window does not apply to approved templates.
    """
    conversation, lead = _load_conversation_and_lead(session, conversation_id, context=None)

    if idempotency_key:
        existing = _find_idempotent_message(session, conversation.tenant_id, idempotency_key)
        if existing is not None:
            return _replay_or_conflict(existing, conversation.id)

    ensure_not_opted_out(lead)
    ensure_whatsapp_conversation(conversation)

    template = TemplatePayload(name=name, language=language, params=params or [])
    token, phone_number_id = _resolve_credentials(session, conversation.tenant_id)

    sent, _replay = await _persist_and_send(
        session=session,
        conversation=conversation,
        lead=lead,
        text=None,
        payload=build_template_payload(template.name, template.language, template.params),
        idempotency_key=idempotency_key,
        token=token,
        phone_number_id=phone_number_id,
    )
    return sent
