"""enable rls and create crm_app role

Revision ID: d4525a56666f
Revises: c3a8d5e17f42
Create Date: 2026-11-10 03:58:34.705182

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4525a56666f'
down_revision: Union[str, Sequence[str], None] = 'c3a8d5e17f42'
depends_on: Union[str, Sequence[str], None] = None


GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
USER_GUC = "NULLIF(current_setting('app.user_id', true), '')::uuid"

# Tables that only need the standard tenant-isolation policy.
STANDARD = [
    "teams", "invitations", "leads", "contacts", "interactions", "conversations",
    "messages", "lead_assessments", "tasks", "integrations", "webhook_events",
]

# Tables that have a tenant_id column but are deliberately NOT tenant-isolated
# (DATABASE_SCHEMA.md section 13: auth tables run before a tenant is chosen).
EXEMPT = {"refresh_tokens"}

INVITATION_TOKEN_GUC = "NULLIF(current_setting('app.invitation_token_hash', true), '')"


def _existing(conn):
    rows = conn.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    return {r[0] for r in rows}


def _enable(t):
    op.execute(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY')


def upgrade() -> None:
    conn = op.get_bind()
    existing = _existing(conn)

    # 1. Application role: cannot bypass RLS. Its password is set outside Git.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
                CREATE ROLE crm_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO crm_app")
    for t in sorted(existing - {"alembic_version"}):
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{t}" TO crm_app')
    if "tenants" in existing:
        op.execute("REVOKE DELETE ON tenants FROM crm_app")
    if "audit_logs" in existing:
        op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM crm_app")

    # 2. Standard policy: a row is visible/writable only for the verified tenant.
    for t in STANDARD:
        if t in existing:
            _enable(t)
            op.execute(
                f'CREATE POLICY {t}_tenant_isolation ON "{t}" TO crm_app '
                f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
            )

    # Invitation acceptance resolves one pending token before tenant context exists.
    if "invitations" in existing:
        op.execute(
            "CREATE POLICY invitations_token_lookup ON invitations "
            f"FOR SELECT TO crm_app USING (token_hash = {INVITATION_TOKEN_GUC} "
            "AND expires_at > now() AND accepted_at IS NULL AND status = 'pending')"
        )

    # 3. Special tables (DATABASE_SCHEMA.md section 13).
    if "tenant_memberships" in existing:
        _enable("tenant_memberships")
        op.execute(
            f"CREATE POLICY tenant_memberships_tenant_isolation ON tenant_memberships TO crm_app "
            f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
        )
        # A user may list THEIR OWN memberships before choosing a tenant.
        op.execute(
            f"CREATE POLICY memberships_self_lookup ON tenant_memberships "
            f"FOR SELECT TO crm_app USING (is_active AND user_id = {USER_GUC})"
        )
    if "tenants" in existing:
        _enable("tenants")
        op.execute(
            f"CREATE POLICY tenants_tenant_isolation ON tenants FOR ALL TO crm_app "
            f"USING (id = {GUC}) WITH CHECK (id = {GUC})"
        )
        op.execute(
            f"CREATE POLICY tenants_membership_lookup ON tenants FOR SELECT TO crm_app "
            f"USING (id IN (SELECT tm.tenant_id FROM tenant_memberships tm "
            f"WHERE tm.user_id = {USER_GUC} AND tm.is_active))"
        )
    if "audit_logs" in existing:
        _enable("audit_logs")
        op.execute(
            f"CREATE POLICY audit_logs_tenant_isolation ON audit_logs TO crm_app "
            f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
        )
        # Platform/login events have no tenant yet: allow INSERT only.
        op.execute(
            "CREATE POLICY audit_logs_platform_insert ON audit_logs "
            "FOR INSERT TO crm_app WITH CHECK (tenant_id IS NULL)"
        )

    # 4. Safety net: fail the migration if any tenant table was missed.
    missing = conn.execute(sa.text("""
        SELECT DISTINCT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN information_schema.columns col
          ON col.table_schema = n.nspname AND col.table_name = c.relname
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND col.column_name = 'tenant_id'
          AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
    """)).scalars().all()
    missing = sorted(set(missing) - EXEMPT)
    if missing:
        raise RuntimeError(f"Tenant tables without RLS: {missing}")


def downgrade() -> None:
    conn = op.get_bind()
    existing = _existing(conn)
    migration_policies = {
        t: {f"{t}_tenant_isolation"} for t in STANDARD
    }
    migration_policies.update(
        {
            "tenant_memberships": {
                "tenant_memberships_tenant_isolation",
                "memberships_self_lookup",
            },
            "tenants": {
                "tenants_tenant_isolation",
                "tenants_membership_lookup",
            },
            "audit_logs": {
                "audit_logs_tenant_isolation",
                "audit_logs_platform_insert",
            },
        }
    )
    for t, policy_names in migration_policies.items():
        if t not in existing:
            continue
        present = set(
            conn.execute(
                sa.text(
                    "SELECT policyname FROM pg_policies "
                    "WHERE schemaname = 'public' AND tablename = :t"
                ),
                {"t": t},
            ).scalars()
        )
        created_here = present & policy_names
        for p in created_here:
            op.execute(f'DROP POLICY "{p}" ON "{t}"')
        if created_here and not (present - created_here):
            op.execute(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY')
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
                DROP OWNED BY crm_app;
                DROP ROLE crm_app;
            END IF;
        END
        $$;
    """)