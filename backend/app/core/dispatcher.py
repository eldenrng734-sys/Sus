"""n8n event dispatcher runner and webhook delivery (#8).

Place at: backend/app/core/dispatcher.py

Claims pending n8n-bound rows from outbox_events using FOR UPDATE SKIP LOCKED
and POSTs them to the configured n8n webhook URL with HMAC-SHA256 signatures:
  X-Event-ID:  the outbox row id (UUID)
  X-Timestamp: unix epoch timestamp string
  X-Signature: sha256=<hex> of HMAC-SHA256(N8N_EVENT_SIGNING_SECRET, timestamp + '.' + raw_body)

Body rule: IDs and event type only, never PII or message text.
Retries: Exponential backoff; dead after MAX_ATTEMPTS (5); dead events are never auto-retried.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import socket
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("app.dispatcher")

HANDLED_EVENTS = ("lead.created", "lead.replied", "task.due", "task.cancelled")
MAX_ATTEMPTS = 5
LEASE_SECONDS = 300.0  # abandoned 'processing' rows reclaimed after 5 min
BATCH_SIZE = 10
BACKOFF_BASE_SECONDS = 30.0
BACKOFF_CAP_SECONDS = 3600.0

ALLOWED_PAYLOAD_KEYS = {
    "lead_id",
    "conversation_id",
    "message_id",
    "task_id",
    "source",
    "reason",
}

SessionFactory = Callable[[], "Session"]


class DeliveryError(Exception):
    """Raised when n8n webhook delivery fails or returns non-2xx status."""


@dataclass(frozen=True)
class ClaimedDispatcherEvent:
    id: uuid.UUID
    tenant_id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict
    attempts: int


def build_signature(secret: str, timestamp: str, raw_body: str | bytes) -> str:
    """Compute X-Signature = sha256=<hex> of HMAC-SHA256(secret, timestamp + '.' + raw_body)."""
    if not secret:
        raise ValueError("A signing secret is required")
    raw_bytes = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
    to_sign = f"{timestamp}.".encode("utf-8") + raw_bytes
    digest = hmac.new(secret.encode("utf-8"), to_sign, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, timestamp: str, raw_body: str | bytes, signature: str) -> bool:
    """Constant-time comparison against expected signature."""
    try:
        expected = build_signature(secret, timestamp, raw_body)
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def sanitize_payload(payload: dict | None) -> dict:
    """Strip all customer-supplied text and PII. Only IDs and minimal metadata allowed."""
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if k in ALLOWED_PAYLOAD_KEYS and v is not None}


def build_dispatcher_body(event: ClaimedDispatcherEvent) -> str:
    """Format canonical event JSON containing IDs and event type only."""
    body_data = {
        "aggregate_id": str(event.aggregate_id),
        "aggregate_type": event.aggregate_type,
        "event_id": str(event.id),
        "event_type": event.event_type,
        "payload": sanitize_payload(event.payload),
        "tenant_id": str(event.tenant_id),
    }
    return json.dumps(body_data, sort_keys=True)


_CLAIM_SQL = text(
    """
    WITH picked AS (
        SELECT id FROM outbox_events
        WHERE event_type = ANY(:types)
          AND (
                (status = 'pending' AND available_at <= now())
             OR (status = 'processing'
                 AND locked_at < now() - make_interval(secs => CAST(:lease AS double precision)))
          )
        ORDER BY available_at, created_at
        LIMIT :n
        FOR UPDATE SKIP LOCKED
    )
    UPDATE outbox_events e
       SET status = 'processing', locked_at = now(), locked_by = :worker,
           attempts = e.attempts + 1
      FROM picked
     WHERE e.id = picked.id
    RETURNING
        e.id, e.tenant_id, e.event_type, e.aggregate_type,
        e.aggregate_id, e.payload, e.attempts
    """
)


def worker_id() -> str:
    return f"dispatcher:{socket.gethostname()}:{os.getpid()}"


def claim_batch(
    session_factory: SessionFactory,
    *,
    limit: int = BATCH_SIZE,
    worker: str | None = None,
) -> list[ClaimedDispatcherEvent]:
    """Claim a bounded batch of n8n events in one short transaction."""
    with session_factory() as db:
        rows = db.execute(
            _CLAIM_SQL,
            {
                "types": list(HANDLED_EVENTS),
                "lease": LEASE_SECONDS,
                "n": limit,
                "worker": worker or worker_id(),
            },
        ).all()
        db.commit()

    return [
        ClaimedDispatcherEvent(
            id=r.id,
            tenant_id=r.tenant_id,
            event_type=r.event_type,
            aggregate_type=r.aggregate_type,
            aggregate_id=r.aggregate_id,
            payload=r.payload if isinstance(r.payload, dict) else {},
            attempts=r.attempts,
        )
        for r in rows
    ]


def _set_tenant(db: Session, tenant_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )


def _mark(db: Session, event: ClaimedDispatcherEvent, status: str, error: str | None) -> None:
    db.execute(
        text(
            """
            UPDATE outbox_events
               SET status = :s, processed_at = now(), last_error = :e,
                   locked_at = NULL, locked_by = NULL
             WHERE id = :id AND tenant_id = :t
            """
        ),
        {"s": status, "e": error, "id": event.id, "t": event.tenant_id},
    )


def _finish(
    session_factory: SessionFactory,
    event: ClaimedDispatcherEvent,
    status: str,
    error: str | None,
) -> None:
    with session_factory() as db:
        _set_tenant(db, event.tenant_id)
        _mark(db, event, status, error)
        db.commit()


def _fail_or_retry(
    session_factory: SessionFactory,
    event: ClaimedDispatcherEvent,
    exc: Exception,
) -> None:
    code = type(exc).__name__
    if event.attempts >= MAX_ATTEMPTS:
        _finish(session_factory, event, "dead", code)
        return

    delay = min(BACKOFF_BASE_SECONDS * 2 ** (event.attempts - 1), BACKOFF_CAP_SECONDS)
    with session_factory() as db:
        _set_tenant(db, event.tenant_id)
        db.execute(
            text(
                """
                UPDATE outbox_events
                   SET status = 'pending', last_error = :e,
                       available_at = now() + make_interval(secs => CAST(:d AS double precision)),
                       locked_at = NULL, locked_by = NULL
                 WHERE id = :id AND tenant_id = :t
                """
            ),
            {"status": "pending", "e": code, "d": delay, "id": event.id, "t": event.tenant_id},
        )
        db.commit()


def dispatch_event(
    event: ClaimedDispatcherEvent,
    *,
    webhook_url: str,
    signing_secret: str,
    http_client: Any = None,
) -> None:
    """POST event to n8n webhook with X-Event-ID, X-Timestamp, and X-Signature headers."""
    raw_body = build_dispatcher_body(event)
    timestamp = str(int(time.time()))
    signature = build_signature(signing_secret, timestamp, raw_body)

    headers = {
        "X-Event-ID": str(event.id),
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }

    if http_client is not None:
        res = http_client.post(webhook_url, headers=headers, content=raw_body, timeout=10.0)
    else:
        with httpx.Client(timeout=10.0) as client:
            res = client.post(webhook_url, headers=headers, content=raw_body)

    if not getattr(res, "is_success", False) and getattr(res, "status_code", 500) >= 400:
        raise DeliveryError(f"Delivery failed with HTTP {getattr(res, 'status_code', 'unknown')}")


def process_event(
    session_factory: SessionFactory,
    event: ClaimedDispatcherEvent,
    *,
    webhook_url: str,
    signing_secret: str,
    http_client: Any = None,
) -> str:
    """Dispatch one claimed event. Returns 'processed', 'retry', or 'dead'."""
    if event.attempts > MAX_ATTEMPTS:
        _finish(session_factory, event, "dead", "max_attempts_exceeded")
        return "dead"

    try:
        dispatch_event(
            event,
            webhook_url=webhook_url,
            signing_secret=signing_secret,
            http_client=http_client,
        )
        _finish(session_factory, event, "processed", None)
        return "processed"
    except Exception as exc:
        logger.warning(
            "dispatch_failed event=%s event_type=%s error=%s",
            event.id,
            event.event_type,
            type(exc).__name__,
        )
        try:
            _fail_or_retry(session_factory, event, exc)
        except Exception as inner:
            logger.error(
                "dispatch_retry_record_failed event=%s error=%s",
                event.id,
                type(inner).__name__,
            )
        return "dead" if event.attempts >= MAX_ATTEMPTS else "retry"


def run_once(
    session_factory: SessionFactory,
    *,
    webhook_url: str,
    signing_secret: str,
    batch_size: int = BATCH_SIZE,
    http_client: Any = None,
) -> Counter:
    """Claim one batch and dispatch it. Returns count of outcomes."""
    outcomes: Counter = Counter()
    for event in claim_batch(session_factory, limit=batch_size):
        outcome = process_event(
            session_factory,
            event,
            webhook_url=webhook_url,
            signing_secret=signing_secret,
            http_client=http_client,
        )
        outcomes[outcome] += 1
    return outcomes


def run_forever(
    session_factory: SessionFactory,
    *,
    webhook_url: str,
    signing_secret: str,
    poll_seconds: float = 2.0,
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    """Polling loop for the dispatcher service."""
    while not should_stop():
        try:
            handled = sum(
                run_once(
                    session_factory,
                    webhook_url=webhook_url,
                    signing_secret=signing_secret,
                ).values()
            )
        except Exception as exc:
            logger.error("dispatcher_loop_error error=%s", type(exc).__name__)
            handled = 0
        if handled == 0:
            time.sleep(poll_seconds)
