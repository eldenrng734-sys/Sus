"""merge_day7_schema_and_dev2_heads

Revision ID: b381846ed83c
Revises: a1b2c3d4e5f6, c6452d0f8136
Create Date: 2026-11-14 07:55:53.772813

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'b381846ed83c'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'c6452d0f8136')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
