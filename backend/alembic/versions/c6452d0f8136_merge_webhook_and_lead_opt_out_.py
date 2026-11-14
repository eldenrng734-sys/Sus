"""Merge webhook and lead opt-out migration histories.

Revision ID: c6452d0f8136
Revises: a7d3c91e5b20, d7b1f4a6c802
"""

from typing import Sequence, Union

revision: str = "c6452d0f8136"
down_revision: Union[str, Sequence[str], None] = ("a7d3c91e5b20", "d7b1f4a6c802")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
