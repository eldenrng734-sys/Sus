"""create tenant_settings table with forced RLS and quiet hours defaults

Revision ID: 7e1a2b3c4d5e
Revises: 6bc6d10a90da
Create Date: 2026-11-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7e1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "6bc6d10a90da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "timezone",
            sa.String(length=50),
            server_default=sa.text("'Asia/Dhaka'"),
            nullable=False,
        ),
        sa.Column(
            "quiet_hours_start",
            sa.Time(),
            server_default=sa.text("'21:00:00'::time"),
            nullable=False,
        ),
        sa.Column(
            "quiet_hours_end",
            sa.Time(),
            server_default=sa.text("'09:00:00'::time"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.execute('ALTER TABLE "tenant_settings" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "tenant_settings" FORCE ROW LEVEL SECURITY')
    op.execute(
        "CREATE POLICY tenant_settings_tenant_isolation ON tenant_settings TO crm_app "
        f"USING (tenant_id = {TENANT_GUC}) WITH CHECK (tenant_id = {TENANT_GUC})"
    )
    op.execute('GRANT SELECT, INSERT, UPDATE ON "tenant_settings" TO crm_app')
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON "tenant_settings" TO crm_migrator')


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_settings_tenant_isolation ON tenant_settings")
    op.execute('REVOKE SELECT, INSERT, UPDATE ON "tenant_settings" FROM crm_app')
    op.execute('REVOKE SELECT, INSERT, UPDATE, DELETE ON "tenant_settings" FROM crm_migrator')
    op.drop_table("tenant_settings")
