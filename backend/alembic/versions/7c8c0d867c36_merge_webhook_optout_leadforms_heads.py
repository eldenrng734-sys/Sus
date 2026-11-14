"""merge_webhook_optout_leadforms_heads

Revision ID: 7c8c0d867c36
Revises: d7b1f4a6c802, f4a91c6d2b37
Create Date: 2026-11-14 04:31:12.548495

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "7c8c0d867c36"
down_revision: Union[str, Sequence[str], None] = ("d7b1f4a6c802", "f4a91c6d2b37")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
