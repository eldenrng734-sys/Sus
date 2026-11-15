"""Transactional outbox producer.

Place at: backend/app/core/outbox.py

An event is written in the SAME transaction as the business change, so it exists
only if that change commits. This helper never commits and never opens its own
session. The caller must already have tenant context set (it does: it is
inserting tenant data).

Payload rule: IDs and minimal metadata only. No names, emails, phones or
message text (DATABASE_SCHEMA.md, outbox_events).
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

AGGREGATE_TYPES = ("lead", "conversation", "message", "task", "assessment", "integration")

_INSERT = text(
    """
    INSERT INTO outbox_events
        (tenant_id, event_type, aggregate_type, aggregate_id, payload, idempotency_key)
    VALUES
        (:tenant_id, :event_type, :aggregate_type, :aggregate_id,
         CAST(:payload AS jsonb), :idempotency_key)
    ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
    DO NOTHING
    """
)


def enqueue_event(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    idempotency_key: str,
    payload: dict | None = None,
) -> None:
    """Queue one event. A repeated idempotency_key is silently ignored."""
    if aggregate_type not in AGGREGATE_TYPES:
        raise ValueError(f"unknown aggregate_type: {aggregate_type}")
    db.execute(
        _INSERT,
        {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(payload or {}),
            "idempotency_key": idempotency_key,
        },
    )


def emit_lead_created(db: Session, *, tenant_id: uuid.UUID, lead_id: uuid.UUID, source: str) -> None:
    enqueue_event(
        db,
        tenant_id=tenant_id,
        event_type="lead.created",
        aggregate_type="lead",
        aggregate_id=lead_id,
        idempotency_key=f"lead.created:{lead_id}",
        payload={"lead_id": str(lead_id), "source": source},
    )


def emit_message_received(
    db: Session, *, tenant_id: uuid.UUID, message_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    enqueue_event(
        db,
        tenant_id=tenant_id,
        event_type="message.received",
        aggregate_type="message",
        aggregate_id=message_id,
        idempotency_key=f"message.received:{message_id}",
        payload={"message_id": str(message_id), "conversation_id": str(conversation_id)},
    )