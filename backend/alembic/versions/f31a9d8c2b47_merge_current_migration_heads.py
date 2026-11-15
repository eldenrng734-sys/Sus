"""Merge the current webhook and task migration heads.

Revision ID: f31a9d8c2b47
Revises: a1b2c3d4e5f6, a9431c7d5e20, c6452d0f8136
Create Date: 2026-11-14 14:00:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "f31a9d8c2b47"
down_revision: Union[str, Sequence[str], None] = (
    "a1b2c3d4e5f6",
    "a9431c7d5e20",
    "c6452d0f8136",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration branches without changing the schema."""
    pass


def downgrade() -> None:
    """Leave downgrade behavior to the merged branch revisions."""
    pass
