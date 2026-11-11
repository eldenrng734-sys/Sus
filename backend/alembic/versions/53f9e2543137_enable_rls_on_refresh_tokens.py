"""enable rls on refresh_tokens
Revision ID: 53f9e2543137
Revises: bb2c29e3daac
Create Date: 2026-11-10 07:55:26.496392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53f9e2543137'
down_revision: Union[str, Sequence[str], None] = 'bb2c29e3daac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
