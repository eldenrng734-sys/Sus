"""merge mfa and rls heads

Revision ID: 03482c0cfa0e
Revises: d2e76f7e5fbe, 53f9e2543137
Create Date: 2026-11-12 06:08:24.324200
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "03482c0cfa0e"
down_revision: Union[str, Sequence[str], None] = (
    "d2e76f7e5fbe",
    "53f9e2543137",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge MFA and RLS migration heads."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass