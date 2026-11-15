"""Merge webhook lookup and current integration migration histories.

Revision ID: d9f2a6b8c014
Revises: a1b2c3d4e5f6, c6452d0f8136
"""

from typing import Sequence, Union

revision: str = "d9f2a6b8c014"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f6", "c6452d0f8136")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
