"""Merge provider-native leads and outbox/notifications migration heads.

Revision ID: e6f4a8d1c209
Revises: 9a7c3e1f6b42, e5c9a1d7b3f2
"""

from typing import Sequence, Union

revision: str = "e6f4a8d1c209"
down_revision: Union[str, Sequence[str], None] = ("9a7c3e1f6b42", "e5c9a1d7b3f2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
