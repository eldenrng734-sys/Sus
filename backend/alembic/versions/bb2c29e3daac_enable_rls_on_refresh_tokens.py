"""enable rls on refresh_tokens

Revision ID: bb2c29e3daac
Revises: d4525a56666f
Create Date: 2026-11-10 07:43:11.194883

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "bb2c29e3daac"
down_revision: Union[str, Sequence[str], None] = "d4525a56666f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
