"""Script to inspect and requeue dead outbox events (#14).

Dead events occur when an outbox event reaches MAX_ATTEMPTS (5) and fails.
Because dead events are never auto-retried by the dispatcher, this administrative
tool allows inspecting and requeueing them with an audit log.

Usage:
  python backend/scripts/requeue_dead.py --list
  python backend/scripts/requeue_dead.py --event-id <UUID> [--tenant-id <UUID>]
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import get_engine, set_tenant_context
from app.modules.audit.service import record_audit_event


def list_dead_events(
    session: Session, tenant_id: str | uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """List dead outbox events."""
    if tenant_id:
        set_tenant_context(session, str(tenant_id))
        stmt = text(
            """
            SELECT id, tenant_id, event_type, attempts, last_error, created_at
              FROM outbox_events
             WHERE status = 'dead' AND tenant_id = :t
             ORDER BY created_at ASC
            """
        )
        rows = session.execute(stmt, {"t": str(tenant_id)}).all()
    else:
        stmt = text(
            """
            SELECT id, tenant_id, event_type, attempts, last_error, created_at
              FROM outbox_events
             WHERE status = 'dead'
             ORDER BY created_at ASC
            """
        )
        rows = session.execute(stmt).all()

    events = []
    for r in rows:
        events.append(
            {
                "id": str(r.id),
                "tenant_id": str(r.tenant_id),
                "event_type": str(r.event_type),
                "attempts": int(r.attempts),
                "last_error": str(r.last_error or ""),
                "created_at": str(r.created_at),
            }
        )
    return events


def requeue_dead_event(
    session: Session,
    event_id: str | uuid.UUID,
    tenant_id: str | uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Requeue a dead outbox event and record an audit log."""
    ev_uuid = uuid.UUID(str(event_id))

    if tenant_id:
        t_uuid = uuid.UUID(str(tenant_id))
        set_tenant_context(session, str(t_uuid))
        row = session.execute(
            text(
                """
                SELECT id, tenant_id, event_type, attempts, last_error
                  FROM outbox_events
                 WHERE id = :id AND tenant_id = :t
                """
            ),
            {"id": ev_uuid, "t": t_uuid},
        ).first()
    else:
        row = session.execute(
            text(
                """
                SELECT id, tenant_id, event_type, attempts, last_error
                  FROM outbox_events
                 WHERE id = :id
                """
            ),
            {"id": ev_uuid},
        ).first()

    if row is None:
        return None

    actual_tenant_id = row.tenant_id
    set_tenant_context(session, str(actual_tenant_id))

    session.execute(
        text(
            """
            UPDATE outbox_events
               SET status = 'pending',
                   attempts = 0,
                   available_at = now(),
                   last_error = NULL,
                   locked_at = NULL,
                   locked_by = NULL
             WHERE id = :id AND tenant_id = :t
            """
        ),
        {"id": ev_uuid, "t": actual_tenant_id},
    )

    record_audit_event(
        session,
        action="outbox.requeue",
        actor_type="platform_admin",
        tenant_id=actual_tenant_id,
        entity_type="outbox_event",
        entity_id=ev_uuid,
        details={
            "event_type": row.event_type,
            "previous_attempts": row.attempts,
            "last_error": row.last_error,
        },
    )

    session.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(actual_tenant_id),
        "event_type": str(row.event_type),
        "previous_attempts": row.attempts,
        "last_error": row.last_error,
        "status": "pending",
    }


def main():
    parser = argparse.ArgumentParser(description="Inspect and requeue dead outbox events")
    parser.add_argument("--list", action="store_true", help="List all dead outbox events")
    parser.add_argument("--event-id", help="Outbox event UUID to requeue")
    parser.add_argument("--tenant-id", help="Optional tenant UUID filter")

    args = parser.parse_args()

    engine = get_engine()
    with Session(engine) as session:
        if args.event_id:
            res = requeue_dead_event(session, args.event_id, tenant_id=args.tenant_id)
            if res is None:
                print(f"Error: Event {args.event_id} not found.")
                sys.exit(1)
            print(f"[+] Requeued dead event {res['id']}:")
            print(f"    Tenant: {res['tenant_id']}")
            print(f"    Event Type: {res['event_type']}")
            print(f"    Previous Attempts: {res['previous_attempts']}")
            print(f"    Last Error: {res['last_error']}")
            print("    Status: pending (ready for dispatcher pickup)")
        else:
            events = list_dead_events(session, tenant_id=args.tenant_id)
            if not events:
                print("No dead outbox events found.")
                return
            print(f"Found {len(events)} dead outbox event(s):")
            print("-" * 80)
            for ev in events:
                print(
                    f"ID: {ev['id']} | Type: {ev['event_type']} | "
                    f"Attempts: {ev['attempts']} | Error: {ev['last_error']}"
                )
            print("-" * 80)


if __name__ == "__main__":
    main()
