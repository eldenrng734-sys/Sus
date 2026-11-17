"""merge_provider_native_leads_head

Revision ID: 4187cdb58db1
Revises: 9a7c3e1f6b42, e5c9a1d7b3f2
Create Date: 2026-11-17 12:30:37.002647

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "4187cdb58db1"
down_revision: Union[str, Sequence[str], None] = ("9a7c3e1f6b42", "e5c9a1d7b3f2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
