"""Server-side round-robin lead assignment.

Rules (API_CONTRACT 8.5, DATABASE_SCHEMA `assignment_cursors`):

- A lead is only handed to an active sales rep of the same tenant and team.
- The rotation position is stored once per (tenant, team) in `assignment_cursors`.
- The lead row and the cursor row are locked, so two concurrent requests can never
  pick the same position. Assignment, timeline event, audit record and cursor update
  all live in the caller's transaction and succeed or roll back together.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.audit.service import record_audit_event
from app.modules.leads.models import AssignmentCursor, Interaction, Lead
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User

# Only sales representatives take part in the rotation. Managers and admins
# supervise teams and are assigned explicitly when needed.
ELIGIBLE_ROLES = ("rep",)
ROTATION_METHOD = "round_robin"


@dataclass(frozen=True)
class AssignmentResult:
    """The rep that received the lead, plus the cursor state after the move."""

    user_id: uuid.UUID
    team_id: uuid.UUID
    previous_user_id: uuid.UUID | None


def next_rep(
    rep_ids: Sequence[uuid.UUID],
    last_user_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Return the rep after ``last_user_id`` and wrap around at the end."""
    ordered = list(rep_ids)
    if not ordered:
        return None
    if last_user_id is None or last_user_id not in ordered:
        return ordered[0]
    return ordered[(ordered.index(last_user_id) + 1) % len(ordered)]


def _eligible_reps(
    session: Session,
    tenant_id: uuid.UUID,
    team_id: uuid.UUID,
) -> list[tuple[uuid.UUID, datetime, uuid.UUID]]:
    """Active reps of this tenant and team, in join order."""
    rows = session.execute(
        select(
            TenantMembership.user_id,
            TenantMembership.created_at,
            TenantMembership.id,
        )
        .join(User, User.id == TenantMembership.user_id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.team_id == team_id,
            TenantMembership.is_active.is_(True),
            TenantMembership.role.in_(ELIGIBLE_ROLES),
            User.is_active.is_(True),
        )
        .order_by(TenantMembership.created_at, TenantMembership.id)
    ).all()
    return [(row.user_id, row.created_at, row.id) for row in rows]


def _last_position(
    session: Session,
    tenant_id: uuid.UUID,
    last_user_id: uuid.UUID | None,
) -> tuple[datetime, uuid.UUID] | None:
    """Join position of the previous rep, even if they are no longer eligible."""
    if last_user_id is None:
        return None
    row = session.execute(
        select(TenantMembership.created_at, TenantMembership.id).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == last_user_id,
        )
    ).first()
    return (row.created_at, row.id) if row is not None else None


def _select_next(
    session: Session,
    tenant_id: uuid.UUID,
    reps: list[tuple[uuid.UUID, datetime, uuid.UUID]],
    last_user_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if not reps:
        return None
    if last_user_id is None or any(rep[0] == last_user_id for rep in reps):
        return next_rep([rep[0] for rep in reps], last_user_id)

    # The previous rep left the team or was deactivated: continue with the next
    # eligible rep after their position instead of restarting the rotation.
    position = _last_position(session, tenant_id, last_user_id)
    if position is not None:
        for user_id, created_at, membership_id in reps:
            if (created_at, membership_id) > position:
                return user_id
    return reps[0][0]


def _lock_cursor(session: Session, tenant_id: uuid.UUID, team_id: uuid.UUID) -> AssignmentCursor:
    """Create the rotation row if it is missing, then lock it for this transaction.

    The upsert makes concurrent creation safe: the loser of the insert race waits
    for the winner, then the SELECT ... FOR UPDATE queues behind it.
    """
    session.execute(
        pg_insert(AssignmentCursor)
        .values(tenant_id=tenant_id, team_id=team_id)
        .on_conflict_do_nothing(constraint="uq_assignment_cursors_tenant_team")
    )
    cursor = session.scalar(
        select(AssignmentCursor)
        .where(
            AssignmentCursor.tenant_id == tenant_id,
            AssignmentCursor.team_id == team_id,
        )
        .with_for_update()
    )
    if cursor is None:  # pragma: no cover - the upsert above guarantees the row
        raise RuntimeError("Assignment cursor could not be locked")
    return cursor


def assign_round_robin(
    session: Session,
    *,
    lead: Lead,
    team_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> AssignmentResult | None:
    """Assign ``lead`` to the next eligible rep inside the caller's transaction.

    Returns ``None`` without touching the cursor when the lead already has an
    owner or when the team has no eligible rep. The caller owns commit/rollback.
    """
    if lead.assigned_user_id is not None:
        return None

    cursor = _lock_cursor(session, lead.tenant_id, team_id)
    reps = _eligible_reps(session, lead.tenant_id, team_id)
    next_user_id = _select_next(session, lead.tenant_id, reps, cursor.last_assigned_user_id)
    if next_user_id is None:
        return None

    previous_user_id = lead.assigned_user_id
    lead.assigned_user_id = next_user_id
    lead.team_id = team_id
    lead.version += 1
    cursor.last_assigned_user_id = next_user_id

    session.add(
        Interaction(
            tenant_id=lead.tenant_id,
            lead_id=lead.id,
            type="assigned",
            source="automation",
            details={
                "assigned_user_id": str(next_user_id),
                "team_id": str(team_id),
                "method": ROTATION_METHOD,
            },
            created_by_user_id=actor_user_id,
        )
    )
    record_audit_event(
        session,
        action="lead.assigned",
        actor_type="automation",
        tenant_id=lead.tenant_id,
        actor_user_id=actor_user_id,
        entity_type="lead",
        entity_id=lead.id,
        details={
            "assigned_user_id": str(next_user_id),
            "team_id": str(team_id),
            "method": ROTATION_METHOD,
        },
    )
    return AssignmentResult(
        user_id=next_user_id,
        team_id=team_id,
        previous_user_id=previous_user_id,
    )
