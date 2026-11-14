"""merge lead opt out and lead forms heads

Revision ID: e22809c75866
Revises: d7b1f4a6c802, f4a91c6d2b37
Create Date: 2026-11-14 10:32:04.712854

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "e22809c75866"
down_revision: Union[str, Sequence[str], None] = ("d7b1f4a6c802", "f4a91c6d2b37")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
