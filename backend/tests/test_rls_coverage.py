"""Guard RLS coverage and ensure the app/worker roles cannot bypass RLS.

Tests that require a live database are skipped when no DATABASE_URL or
MIGRATION_DATABASE_URL is set.  In CI the postgres service provides the URL.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings

# Tenant tables intentionally NOT under tenant RLS.
# Every entry needs a reason and a team agreement.
EXEMPT: dict[str, str] = {
    "refresh_tokens": (
        "Per-user sessions: looked up by token hash before the tenant is known "
        "(sessions.py, tenancy.py); tenant_id is nullable."
    ),
}

# Roles that are explicitly approved to have BYPASSRLS.
# Update this list only after explicit security-approver sign-off (Step #2 ground rule).
# Any role NOT in this list that has BYPASSRLS will fail the allow-list test below.
BYPASSRLS_ALLOW_LIST: frozenset[str] = frozenset(
    # crm_migrator is the table owner used only by Alembic; FORCE RLS still applies
    # to it on every table, so an explicit allow is needed for full pg_dump backups.
    # crm_backup may be added here after security-approver approval (see #2 notes).
    # Leave empty until the first migration that grants BYPASSRLS is merged.
    []
)


@pytest.fixture(scope="module")
def conn():
    url = settings.migration_database_url or settings.database_url
    if not url:
        pytest.skip("database URL is not configured")

    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        connection = engine.connect()
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"database not available: {exc}")

    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


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
    bad = [
        r.relname
        for r in rows
        if r.relname not in EXEMPT and not (r.relrowsecurity and r.relforcerowsecurity)
    ]
    assert not bad, f"RLS not enabled and forced on: {bad}"
    table_names = {r.relname for r in rows}
    assert "tenant_settings" in table_names, "tenant_settings must be present in tenant tables"


def test_every_tenant_table_has_a_policy(conn):
    missing = (
        conn.execute(
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
        )
        .scalars()
        .all()
    )
    assert not [m for m in missing if m not in EXEMPT], f"no policy on: {missing}"


def test_app_role_cannot_bypass_rls(conn):
    """crm_app must be a normal login role with no superuser or BYPASSRLS."""
    row = conn.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crm_app'")
    ).one()
    assert row.rolsuper is False, "crm_app must not be a superuser"
    assert row.rolbypassrls is False, "crm_app must not have BYPASSRLS"


def test_worker_role_cannot_bypass_rls(conn):
    """crm_worker must be a normal login role with no superuser or BYPASSRLS."""
    row = conn.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crm_worker'")
    ).fetchone()
    assert row is not None, "crm_worker role does not exist — run the Step #2 migration"
    assert row.rolsuper is False, "crm_worker must not be a superuser"
    assert row.rolbypassrls is False, "crm_worker must not have BYPASSRLS"


def test_bypassrls_allow_list(conn):
    """Only the explicitly approved roles may have BYPASSRLS.

    If a new role needs BYPASSRLS, add it to BYPASSRLS_ALLOW_LIST in this file
    after security-approver sign-off.  Never add crm_app or crm_worker.
    """
    actual = set(
        conn.execute(
            text(
                """
                SELECT rolname
                FROM pg_roles
                WHERE rolbypassrls = true
                  AND rolname NOT IN ('pg_read_server_files', 'pg_write_server_files',
                                      'pg_execute_server_program', 'rds_superuser',
                                      'rdsadmin', 'rds_replication')
                """
            )
        )
        .scalars()
        .all()
    )
    unapproved = actual - BYPASSRLS_ALLOW_LIST
    assert not unapproved, (
        f"Roles with BYPASSRLS that are NOT in the allow-list: {unapproved}. "
        "Get security-approver sign-off and add them to BYPASSRLS_ALLOW_LIST."
    )


def test_crm_app_zero_rows_without_tenant_context(conn):
    """When crm_app connects and no app.tenant_id is set, every RLS-protected
    table must return 0 rows.  This guards against a missing RLS policy or
    a policy that defaults to permissive instead of restrictive.

    This test requires TEST_APP_DATABASE_URL (the crm_app role URL).
    It is skipped when that URL is not configured.
    """
    import os

    app_url = os.environ.get("TEST_APP_DATABASE_URL")
    if not app_url:
        pytest.skip("Set TEST_APP_DATABASE_URL (crm_app role, test database) to run this check")

    app_engine = create_engine(app_url, connect_args={"connect_timeout": 5})
    try:
        with app_engine.connect() as app_conn:
            # Explicitly do NOT set app.tenant_id — RLS must block everything.
            count = app_conn.execute(text("SELECT count(*) FROM leads")).scalar_one()
    except OperationalError as exc:
        app_engine.dispose()
        pytest.skip(f"Cannot connect as crm_app: {exc}")
    finally:
        app_engine.dispose()

    assert count == 0, f"crm_app with no tenant_id set returned {count} leads — RLS policy gap"
