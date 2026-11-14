"""Create tenant-scoped tasks used by assessment follow-up rules.

Revision ID: a9431c7d5e20
Revises: e22809c75866
Create Date: 2026-11-14 11:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9431c7d5e20"
down_revision: Union[str, Sequence[str], None] = "e22809c75866"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "approval_status",
            sa.Text(),
            server_default="not_required",
            nullable=False,
        ),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), server_default="user", nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('call','meeting','reminder','follow_up')", name="type"),
        sa.CheckConstraint(
            "status IN ('open','done','cancelled','paused')",
            name="status",
        ),
        sa.CheckConstraint(
            "approval_status IN ('not_required','pending','approved','rejected')",
            name="approval_status",
        ),
        sa.CheckConstraint(
            "created_by IN ('user','system','automation')",
            name="created_by",
        ),
        sa.CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)",
            name="done_completed_at",
        ),
        sa.CheckConstraint(
            "(requires_approval = false AND approval_status = 'not_required') "
            "OR (requires_approval = true "
            "AND approval_status IN ('pending','approved','rejected'))",
            name="approval_consistent",
        ),
        sa.CheckConstraint(
            "approval_status <> 'approved' "
            "OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_fields",
        ),
        sa.CheckConstraint(
            "approval_status <> 'rejected' "
            "OR (rejected_by_user_id IS NOT NULL AND rejected_at IS NOT NULL)",
            name="rejected_fields",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tasks_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["leads.tenant_id", "leads.id"],
            name="fk_tasks_lead_leads",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_tasks_assigned_user_tenant_memberships",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "approved_by_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_tasks_approved_by_tenant_memberships",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rejected_by_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_tasks_rejected_by_tenant_memberships",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            name="fk_tasks_team_teams",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tasks_tenant_id_id"),
    )
    op.create_index(
        "uq_tasks_tenant_idempotency",
        "tasks",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_tasks_tenant_assignee_due_open",
        "tasks",
        ["tenant_id", "assigned_user_id", "due_at"],
        unique=False,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_tasks_tenant_status_due",
        "tasks",
        ["tenant_id", "status", "due_at"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_tenant_lead_due",
        "tasks",
        ["tenant_id", "lead_id", "due_at"],
        unique=False,
    )

    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON "tasks" TO crm_app')
    op.execute('ALTER TABLE "tasks" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "tasks" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY tasks_tenant_isolation ON "tasks" TO crm_app '
        f"USING (tenant_id = {TENANT_GUC}) WITH CHECK (tenant_id = {TENANT_GUC})"
    )


def downgrade() -> None:
    op.drop_table("tasks")
