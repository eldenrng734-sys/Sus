"""Guard: every tenant table must have RLS enabled and forced, and the app role must not bypass it."""
import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings

# Tenant tables intentionally NOT under tenant RLS. Every entry needs a reason and a team agreement.
EXEMPT: dict[str, str] = {
    "refresh_tokens": (
        "Per-user sessions: looked up by token hash before the tenant is known "
        "(sessions.py, tenancy.py); tenant_id is nullable."
    ),
}


@pytest.fixture(scope="module")
def conn():
    url = settings.migration_database_url or settings.database_url
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            yield c
    except Exception as exc:  # database not reachable
        pytest.skip(f"database not available: {exc}")


def test_every_tenant_table_has_forced_rls(conn):
    rows = conn.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN information_schema.columns col
              ON col.table_schema = 'public'
             AND col.table_name = c.relname
             AND col.column_name = 'tenant_id'
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
            """
        )
    ).all()
    assert rows, "no tenant tables found: migrations not applied?"
    bad = [r.relname for r in rows if r.relname not in EXEMPT
           and not (r.relrowsecurity and r.relforcerowsecurity)]
    assert not bad, f"RLS not enabled and forced on: {bad}"


def test_every_tenant_table_has_a_policy(conn):
    missing = conn.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN information_schema.columns col
              ON col.table_schema = 'public'
             AND col.table_name = c.relname
             AND col.column_name = 'tenant_id'
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
              AND NOT EXISTS (
                SELECT 1 FROM pg_policies p
                WHERE p.schemaname = 'public' AND p.tablename = c.relname)
            """
        )
    ).scalars().all()
    assert not [m for m in missing if m not in EXEMPT], f"no policy on: {missing}"


def test_app_role_cannot_bypass_rls(conn):
    row = conn.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crm_app'")
    ).one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False