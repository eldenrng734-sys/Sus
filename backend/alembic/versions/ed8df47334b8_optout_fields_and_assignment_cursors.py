"""enforce opt-out timestamps and add tenant-scoped assignment cursors

Revision ID: ed8df47334b8
Revises: e3a2b7c9d140
Create Date: 2026-11-13 11:03:04.530537

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ed8df47334b8"
down_revision: Union[str, Sequence[str], None] = "e3a2b7c9d140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE leads
        SET opted_out_at = COALESCE(opted_out_at, updated_at, now())
        WHERE opted_out AND opted_out_at IS NULL
        """
    )
    op.create_check_constraint(
        "opted_out_timestamp_required",
        "leads",
        "NOT opted_out OR opted_out_at IS NOT NULL",
    )

    op.create_table(
        "assignment_cursors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "last_assigned_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_assignment_cursors_last_assigned_member",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            name="fk_assignment_cursors_team",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assignment_cursors"),
        sa.UniqueConstraint(
            "tenant_id",
            "team_id",
            name="uq_assignment_cursors_tenant_team",
        ),
    )
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON "assignment_cursors" TO crm_app')
    op.execute('ALTER TABLE "assignment_cursors" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "assignment_cursors" FORCE ROW LEVEL SECURITY')
    tenant_guc = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    op.execute(
        "CREATE POLICY assignment_cursors_tenant_isolation ON assignment_cursors TO crm_app "
        f"USING (tenant_id = {tenant_guc}) WITH CHECK (tenant_id = {tenant_guc})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS assignment_cursors_tenant_isolation ON assignment_cursors")
    op.drop_table("assignment_cursors")
    op.drop_constraint(
        "ck_leads_opted_out_timestamp_required",
        "leads",
        type_="check",
    )
