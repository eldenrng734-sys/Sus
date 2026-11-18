"""Add platform admin SECURITY DEFINER functions for cross-tenant management.

Revision ID: 9b3c4d5e6f7a
Revises: 8f2b3c4d5e6f
Create Date: 2026-11-18

"""

from typing import Sequence, Union

from alembic import op

revision: str = "9b3c4d5e6f7a"
down_revision: Union[str, Sequence[str], None] = "8f2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. platform_list_tenants()
    op.execute("""
        CREATE OR REPLACE FUNCTION platform_list_tenants()
        RETURNS TABLE(
            id uuid,
            name varchar,
            slug varchar,
            status varchar,
            created_at timestamptz,
            member_count bigint
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                t.created_at,
                COALESCE(count(tm.id), 0)::bigint AS member_count
            FROM tenants t
            LEFT JOIN tenant_memberships tm ON tm.tenant_id = t.id AND tm.is_active = true
            GROUP BY t.id, t.name, t.slug, t.status, t.created_at
            ORDER BY t.created_at DESC;
        $$;

        REVOKE ALL ON FUNCTION platform_list_tenants() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION platform_list_tenants() TO crm_app;
    """)

    # 2. platform_get_tenant(uuid)
    op.execute("""
        CREATE OR REPLACE FUNCTION platform_get_tenant(p_id uuid)
        RETURNS TABLE(
            id uuid,
            name varchar,
            slug varchar,
            status varchar,
            created_at timestamptz,
            member_count bigint
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                t.created_at,
                COALESCE(count(tm.id), 0)::bigint AS member_count
            FROM tenants t
            LEFT JOIN tenant_memberships tm ON tm.tenant_id = t.id AND tm.is_active = true
            WHERE t.id = p_id
            GROUP BY t.id, t.name, t.slug, t.status, t.created_at;
        $$;

        REVOKE ALL ON FUNCTION platform_get_tenant(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION platform_get_tenant(uuid) TO crm_app;
    """)

    # 3. platform_suspend_tenant(uuid)
    op.execute("""
        CREATE OR REPLACE FUNCTION platform_suspend_tenant(p_id uuid)
        RETURNS TABLE(
            id uuid,
            name varchar,
            slug varchar,
            status varchar,
            created_at timestamptz,
            member_count bigint
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
            UPDATE tenants
            SET status = 'suspended', updated_at = now()
            WHERE tenants.id = p_id;

            RETURN QUERY
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                t.created_at,
                COALESCE(count(tm.id), 0)::bigint AS member_count
            FROM tenants t
            LEFT JOIN tenant_memberships tm ON tm.tenant_id = t.id AND tm.is_active = true
            WHERE t.id = p_id
            GROUP BY t.id, t.name, t.slug, t.status, t.created_at;
        END;
        $$;

        REVOKE ALL ON FUNCTION platform_suspend_tenant(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION platform_suspend_tenant(uuid) TO crm_app;
    """)

    # 4. platform_get_health()
    op.execute("""
        CREATE OR REPLACE FUNCTION platform_get_health()
        RETURNS TABLE(
            db_connections bigint,
            dead_outbox_count bigint
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT
                (SELECT count(*)::bigint FROM pg_stat_activity) AS db_connections,
                (SELECT count(*)::bigint FROM outbox_events WHERE status = 'dead') AS dead_outbox_count;
        $$;

        REVOKE ALL ON FUNCTION platform_get_health() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION platform_get_health() TO crm_app;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS platform_get_health();")
    op.execute("DROP FUNCTION IF EXISTS platform_suspend_tenant(uuid);")
    op.execute("DROP FUNCTION IF EXISTS platform_get_tenant(uuid);")
    op.execute("DROP FUNCTION IF EXISTS platform_list_tenants();")
