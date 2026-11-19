"""Transactional outbox producer.

Place at: backend/app/core/outbox.py

An event is written in the SAME transaction as the business change, so it exists
only if that change commits. This helper never commits and never opens its own
session. The caller must already have tenant context set (it does: it is
inserting tenant data).

Fan-out rule (#8):
One row per consumer, written in the same transaction as the business change,
each with its own uuid4 idempotency key:
  assessment.requested -> claimed by the AI worker (ai/jobs.py)
  lead.created, lead.replied, task.due, task.cancelled -> claimed by the n8n dispatcher

Payload rule: IDs and minimal metadata only. No names, emails, phones or
message text (DATABASE_SCHEMA.md, outbox_events).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

AGGREGATE_TYPES = ("lead", "conversation", "message", "task", "assessment", "integration")

_INSERT = text(
    """
    INSERT INTO outbox_events
        (tenant_id, event_type, aggregate_type, aggregate_id,
         payload, idempotency_key, available_at)
    VALUES
        (:tenant_id, :event_type, :aggregate_type, :aggregate_id,
         CAST(:payload AS jsonb), :idempotency_key, COALESCE(:available_at, now()))
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
    available_at: datetime | None = None,
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
            "available_at": available_at,
        },
    )


def emit_lead_created(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID,
    source: str,
) -> None:
    """Emit lead creation events.

    Fans out to two independent outbox rows with distinct uuid4 idempotency keys:
    1. assessment.requested -> consumed by AI worker
    2. lead.created         -> consumed by n8n dispatcher
    """
    payload = {"lead_id": str(lead_id), "source": source}

    # 1. AI worker: assessment.requested
    enqueue_event(
        db,
        tenant_id=tenant_id,
        event_type="assessment.requested",
        aggregate_type="lead",
        aggregate_id=lead_id,
        idempotency_key=str(uuid.uuid4()),
        payload=payload,
    )

    # 2. n8n dispatcher: lead.created
    enqueue_event(
        db,
        tenant_id=tenant_id,
        event_type="lead.created",
        aggregate_type="lead",
        aggregate_id=lead_id,
        idempotency_key=str(uuid.uuid4()),
        payload=payload,
    )


def emit_message_received(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    message_id: uuid.UUID,
    conversation_id: uuid.UUID,
    lead_id: uuid.UUID | None = None,
) -> None:
    """Emit inbound message events.

    Fans out to two independent outbox rows with distinct uuid4 idempotency keys:
    1. assessment.requested -> consumed by AI worker
    2. lead.replied         -> consumed by n8n dispatcher
    """
    if lead_id is None:
        row = db.execute(
            text("SELECT lead_id FROM conversations WHERE tenant_id = :t AND id = :c"),
            {"t": str(tenant_id), "c": str(conversation_id)},
        ).scalar()
        if row is not None:
            lead_id = uuid.UUID(str(row)) if not isinstance(row, uuid.UUID) else row

    lead_id_str = str(lead_id) if lead_id is not None else None

    # 1. AI worker: assessment.requested
    enqueue_event(
        db,
        tenant_id=tenant_id,
        event_type="assessment.requested",
        aggregate_type="message",
        aggregate_id=message_id,
        idempotency_key=str(uuid.uuid4()),
        payload={
            "message_id": str(message_id),
            "conversation_id": str(conversation_id),
            "lead_id": lead_id_str,
        },
    )

    # 2. n8n dispatcher: lead.replied
    enqueue_event(
        db,
        tenant_id=tenant_id,
        event_type="lead.replied",
        aggregate_type="conversation",
        aggregate_id=conversation_id,
        idempotency_key=str(uuid.uuid4()),
        payload={
            "lead_id": lead_id_str,
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
        },
    )
