"""Merge outbox and notifications migration heads.

Revision ID: 9a7c3e1f6b42
Revises: 2428cf184bb5, c8d49f2176aa
"""

from typing import Sequence, Union

revision: str = "9a7c3e1f6b42"
down_revision: Union[str, Sequence[str], None] = ("2428cf184bb5", "c8d49f2176aa")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
