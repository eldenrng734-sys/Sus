"""Merge the rubaia and dev migration heads.

Revision ID: f6a8c0d2e491
Revises: d9f2a6b8c014, f31a9d8c2b47
"""

from typing import Sequence, Union


revision: str = "f6a8c0d2e491"
down_revision: Union[str, Sequence[str], None] = ("d9f2a6b8c014", "f31a9d8c2b47")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
