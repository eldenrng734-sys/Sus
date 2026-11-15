"""add tenant-scoped idempotency key to messages

Revision ID: a8c4d2e6f9b1
Revises: d3e4f5a6b7c8
Create Date: 2026-11-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a8c4d2e6f9b1"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("idempotency_key", sa.Text(), nullable=True))
    op.create_index(
        "uq_messages_tenant_idempotency",
        "messages",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_tenant_idempotency", table_name="messages")
    op.drop_column("messages", "idempotency_key")
