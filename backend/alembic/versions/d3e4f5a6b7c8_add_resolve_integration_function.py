"""Add SECURITY DEFINER function resolve_integration for unauthenticated webhooks.

Revision ID: d3e4f5a6b7c8
Revises: b381846ed83c
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "b381846ed83c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create narrow SECURITY DEFINER lookup function.
    # Runs with permissions of function creator (crm_owner / superuser),
    # bypassing RLS on integrations to resolve tenant_id and integration_id
    # for valid inbound webhooks without a JWT.
    op.execute("""
        CREATE OR REPLACE FUNCTION resolve_integration(p_provider text, p_account_id text)
        RETURNS TABLE(tenant_id uuid, integration_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id, id AS integration_id
            FROM integrations
            WHERE provider = p_provider
              AND provider_account_id = p_account_id
              AND status = 'active'
              AND (expires_at IS NULL OR expires_at > now())
            LIMIT 1;
        $$;
    """)

    # Lock down execution: only crm_app may execute it.
    op.execute("""
        REVOKE ALL ON FUNCTION resolve_integration(text, text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION resolve_integration(text, text) TO crm_app;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_integration(text, text);")

