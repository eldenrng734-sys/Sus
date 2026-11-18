"""add crm_worker, crm_migrator and crm_backup roles

Revision ID: 6bc6d10a90da
Revises: 4187cdb58db1
Create Date: 2026-11-17

Roles created here:
  crm_worker   — AI worker and dispatcher; SKIP LOCKED on outbox_events, no BYPASSRLS.
  crm_migrator — Alembic / table owner only; NOLOGIN; subject to FORCE RLS so that
                 application tables are protected even during migrations.
  crm_backup   — Read-only pg_dump role; NOLOGIN; NO BYPASSRLS by default.
                 If a full dump requires BYPASSRLS for FORCE-RLS tables, that grant
                 must be approved by the security approver and added to the
                 BYPASSRLS_ALLOW_LIST in test_rls_coverage.py before being applied.

Passwords are set outside Git via WORKER_DATABASE_URL / BACKUP_DATABASE_URL env vars.
The superuser (POSTGRES_USER) must already exist; this migration runs as that user.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "6bc6d10a90da"
down_revision: Union[str, Sequence[str], None] = "4187cdb58db1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables(conn) -> set[str]:
    rows = conn.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    return {r[0] for r in rows}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _existing_tables(conn)

    # ------------------------------------------------------------------
    # 1. crm_worker — login role, no BYPASSRLS.
    #    Password is set by the DBA from WORKER_DATABASE_URL; we only
    #    CREATE the role here if it doesn't already exist.
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_worker') THEN
                CREATE ROLE crm_worker LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO crm_worker")

    # Grant SELECT+UPDATE on outbox_events so the worker can claim events
    # with FOR UPDATE SKIP LOCKED.  No other table access.
    if "outbox_events" in existing:
        op.execute("GRANT SELECT, UPDATE ON outbox_events TO crm_worker")
        # Ensure the worker-claim policy exists (idempotent).
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public'
                      AND tablename  = 'outbox_events'
                      AND policyname = 'outbox_worker_claim'
                ) THEN
                    CREATE POLICY outbox_worker_claim ON outbox_events
                        FOR ALL TO crm_worker USING (true) WITH CHECK (true);
                END IF;
            END
            $$;
        """)

    # ------------------------------------------------------------------
    # 2. crm_migrator — NOLOGIN table owner used only by Alembic.
    #    FORCE RLS still applies to it because we set it on each table,
    #    so it cannot read another tenant's data during migration work.
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_migrator') THEN
                CREATE ROLE crm_migrator NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO crm_migrator")
    # crm_migrator needs full DML on all tables to run migrations.
    for t in sorted(existing - {"alembic_version"}):
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{t}" TO crm_migrator')
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO crm_migrator")

    # ------------------------------------------------------------------
    # 3. crm_backup — NOLOGIN read-only role for pg_dump.
    #    No BYPASSRLS by default.  If FORCE RLS prevents a full logical
    #    dump, the security approver must explicitly approve a BYPASSRLS
    #    grant, add it to BYPASSRLS_ALLOW_LIST in test_rls_coverage.py,
    #    and apply it in a separate migration.
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_backup') THEN
                CREATE ROLE crm_backup NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO crm_backup")
    for t in sorted(existing - {"alembic_version"}):
        op.execute(f'GRANT SELECT ON "{t}" TO crm_backup')


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_backup') THEN
                DROP OWNED BY crm_backup;
                DROP ROLE crm_backup;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_migrator') THEN
                DROP OWNED BY crm_migrator;
                DROP ROLE crm_migrator;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_worker') THEN
                DROP OWNED BY crm_worker;
                DROP ROLE crm_worker;
            END IF;
        END
        $$;
    """)
