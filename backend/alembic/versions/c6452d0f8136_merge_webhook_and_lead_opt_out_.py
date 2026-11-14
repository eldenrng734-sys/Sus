"""merge webhook and lead opt-out migrations

Revision ID: c6452d0f8136
Revises: a7d3c91e5b20, d7b1f4a6c802
Create Date: 2026-11-14 09:53:12.893572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6452d0f8136'
down_revision: Union[str, Sequence[str], None] = ('a7d3c91e5b20', 'd7b1f4a6c802')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
