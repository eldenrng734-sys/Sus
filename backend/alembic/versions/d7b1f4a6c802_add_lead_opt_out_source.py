"""Store the source of a lead opt-out.

Revision ID: d7b1f4a6c802
Revises: ed8df47334b8
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d7b1f4a6c802"
down_revision: Union[str, Sequence[str], None] = "ed8df47334b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("opted_out_source", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "opted_out_source")
