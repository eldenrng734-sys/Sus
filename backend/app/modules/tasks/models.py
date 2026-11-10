import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import app.database.registry  # noqa: F401

from app.database.base import Base, TimestampMixin, UUIDPkMixin

MEMBERSHIP_COLS = ["tenant_memberships.tenant_id", "tenant_memberships.user_id"]


class Task(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    approval_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="not_required"
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[str | None] = mapped_column(Text)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tasks_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_tasks_tenant_id_tenants", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "lead_id"], ["leads.tenant_id", "leads.id"],
            name="fk_tasks_lead_leads", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"], MEMBERSHIP_COLS,
            name="fk_tasks_assigned_user_tenant_memberships", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "approved_by_user_id"], MEMBERSHIP_COLS,
            name="fk_tasks_approved_by_tenant_memberships", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "rejected_by_user_id"], MEMBERSHIP_COLS,
            name="fk_tasks_rejected_by_tenant_memberships", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "team_id"], ["teams.tenant_id", "teams.id"],
            name="fk_tasks_team_teams", ondelete="RESTRICT",
        ),
        CheckConstraint("type IN ('call','meeting','reminder','follow_up')", name="type"),
        CheckConstraint("status IN ('open','done','cancelled','paused')", name="status"),
        CheckConstraint(
            "approval_status IN ('not_required','pending','approved','rejected')",
            name="approval_status",
        ),
        CheckConstraint("created_by IN ('user','system','automation')", name="created_by"),
        CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)", name="done_completed_at"
        ),
        CheckConstraint(
            "(requires_approval = false AND approval_status = 'not_required') "
            "OR (requires_approval = true "
            "AND approval_status IN ('pending','approved','rejected'))",
            name="approval_consistent",
        ),
        CheckConstraint(
            "approval_status <> 'approved' "
            "OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_fields",
        ),
        CheckConstraint(
            "approval_status <> 'rejected' "
            "OR (rejected_by_user_id IS NOT NULL AND rejected_at IS NOT NULL)",
            name="rejected_fields",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_leads_tenant_id_id"),
        Index(
            "uq_tasks_tenant_idempotency", "tenant_id", "idempotency_key",
            unique=True, postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_tasks_tenant_assignee_due_open",
            "tenant_id", "assigned_user_id", "due_at",
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_tasks_tenant_status_due", "tenant_id", "status", "due_at"),
        Index("ix_tasks_tenant_lead_due", "tenant_id", "lead_id", "due_at"),
    )