"""Add restricted integration lookup for incoming webhooks."""

from alembic import op
from sqlalchemy import text


revision = "a7d3c91e5b20"
down_revision = "e3a2b7c9d140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One active external account must belong to only one tenant.
    op.create_index(
        "uq_integrations_active_provider_account",
        "integrations",
        ["provider", "provider_account_id"],
        unique=True,
        postgresql_where=text("status = 'active'"),
    )

    # Allow the trusted webhook handler to resolve an account
    # before setting the tenant context.
    op.execute("""
        CREATE POLICY integrations_webhook_lookup
        ON public.integrations
        FOR SELECT
        TO crm_app
        USING (
            provider = NULLIF(
                current_setting('app.webhook_provider', true),
                ''
            )
            AND provider_account_id = NULLIF(
                current_setting('app.webhook_account_id', true),
                ''
            )
            AND status = 'active'
            AND (
                expires_at IS NULL
                OR expires_at > now()
            )
        )
    """)


def downgrade() -> None:
    op.execute("""
        DROP POLICY IF EXISTS integrations_webhook_lookup
        ON public.integrations
    """)

    op.drop_index(
        "uq_integrations_active_provider_account",
        table_name="integrations",
    )
