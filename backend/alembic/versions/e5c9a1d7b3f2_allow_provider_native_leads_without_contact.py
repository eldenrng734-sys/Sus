"""allow provider-native leads without email or phone

Meta Lead Ads and Messenger contacts are identified by a provider ID
(leadgen_id / page-scoped sender ID) and may legitimately arrive without an
email address or phone number. They are still real, deduplicable leads, so the
contact constraint now allows exactly those two sources when external_id is set.

Revision ID: e5c9a1d7b3f2
Revises: a8c4d2e6f9b1
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5c9a1d7b3f2"
down_revision: str | Sequence[str] | None = "a8c4d2e6f9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The original constraint was created through SQLAlchemy's naming convention,
# which prefixed the already-prefixed name. Keep the exact database name so the
# ORM model and the live schema stay aligned.
CONSTRAINT = "ck_leads_ck_leads_contact_required"


def upgrade() -> None:
    op.execute(f"ALTER TABLE leads DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"""
        ALTER TABLE leads
        ADD CONSTRAINT {CONSTRAINT}
        CHECK (
            email IS NOT NULL
            OR phone IS NOT NULL
            OR (
                source IN ('facebook_lead_ads', 'messenger')
                AND external_id IS NOT NULL
                AND btrim(external_id) <> ''
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE leads DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"""
        ALTER TABLE leads
        ADD CONSTRAINT {CONSTRAINT}
        CHECK (email IS NOT NULL OR phone IS NOT NULL)
        """
    )
