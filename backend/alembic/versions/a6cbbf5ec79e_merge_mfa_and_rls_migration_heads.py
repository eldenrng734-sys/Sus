"""merge MFA and RLS migration heads

Revision ID: a6cbbf5ec79e
Revises: 53f9e2543137, d2e76f7e5fbe
Create Date: 2026-11-11 12:10:32.269637

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "a6cbbf5ec79e"
down_revision: Union[str, Sequence[str], None] = ("53f9e2543137", "d2e76f7e5fbe")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
