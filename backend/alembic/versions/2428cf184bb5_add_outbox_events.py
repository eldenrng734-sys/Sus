"""add outbox_events

Revision ID: 2428cf184bb5
Revises: 1fd32e46d6d9
Create Date: 2026-11-15 10:23:40.263347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2428cf184bb5'
down_revision: Union[str, Sequence[str], None] = '1fd32e46d6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
