"""Create tenant-scoped rep notifications.

Revision ID: c8d49f2176aa
Revises: f6a8c0d2e491
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8d49f2176aa"
down_revision: Union[str, Sequence[str], None] = "f6a8c0d2e491"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('new_lead')", name="ck_notifications_type_valid"),
        sa.CheckConstraint(
            "entity_type IN ('lead')",
            name="ck_notifications_entity_type_valid",
        ),
        sa.CheckConstraint(
            "length(btrim(title)) > 0",
            name="ck_notifications_title_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(body)) > 0",
            name="ck_notifications_body_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_notifications_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_notifications_recipient_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_notifications_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_notifications_tenant_user_created",
        "notifications",
        ["tenant_id", "user_id", "created_at"],
    )
    op.execute('GRANT SELECT, INSERT ON "notifications" TO crm_app')
    op.execute('ALTER TABLE "notifications" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "notifications" FORCE ROW LEVEL SECURITY')
    op.execute(
        "CREATE POLICY notifications_tenant_isolation ON notifications TO crm_app "
        f"USING (tenant_id = {TENANT_GUC}) WITH CHECK (tenant_id = {TENANT_GUC})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS notifications_tenant_isolation ON notifications")
    op.execute('REVOKE SELECT, INSERT ON "notifications" FROM crm_app')
    op.drop_index("ix_notifications_tenant_user_created", table_name="notifications")
    op.drop_table("notifications")
