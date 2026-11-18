"""Add read_at to notifications and grant UPDATE to crm_app.

Revision ID: 8f2b3c4d5e6f
Revises: 7e1a2b3c4d5e
Create Date: 2026-11-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8f2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "7e1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_tenant_user_read",
        "notifications",
        ["tenant_id", "user_id", "read_at"],
    )
    op.execute('GRANT UPDATE ON "notifications" TO crm_app')


def downgrade() -> None:
    op.execute('REVOKE UPDATE ON "notifications" FROM crm_app')
    op.drop_index("ix_notifications_tenant_user_read", table_name="notifications")
    op.drop_column("notifications", "read_at")
