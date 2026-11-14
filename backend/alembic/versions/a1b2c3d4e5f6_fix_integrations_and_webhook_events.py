"""Fix integrations and webhook_events to match spec, and add conversations.external_contact_id.

Changes vs initial_schema:

integrations
- Drop 3-column unique (tenant_id, provider, provider_account_id)
- Add composite unique (tenant_id, id)         → composite FK target
- Add global unique (provider, provider_account_id)  → one account per company
- Rename encrypted_credentials → credentials_encrypted
- Add key_version SmallInteger NOT NULL default 1
- Change scopes JSONB → ARRAY(varchar) with default '{}'
- Tighten String lengths: provider 50→32, provider_account_id 200→128, status 20→16
- Rename check ck_integrations_status_valid → ck_integrations_status
- Add index ix_integrations_tenant_provider

webhook_events
- Add integration_id UUID NOT NULL
- Add composite FK (tenant_id, integration_id) → integrations
- Add attempts INTEGER NOT NULL default 0
- Drop signature_valid column
- Make event_type NOT NULL, tighten String 100→32
- Drop old check ck_webhook_events_status_valid
- Add check ck_webhook_events_status (adds 'processing')
- Drop index ix_webhook_events_tenant_received
- Add index ix_webhook_events_tenant_status (tenant_id, status, received_at)
- Tighten String lengths: provider 50→32, status 20→16

conversations
- Add external_contact_id String(128)

Revision ID: a1b2c3d4e5f6
Revises: 7c8c0d867c36
Create Date: 2026-11-14 10:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "7c8c0d867c36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _col_exists(conn, table: str, col: str) -> bool:
    return (
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": table, "c": col},
        ).scalar()
        is not None
    )


def _con_exists(conn, table: str, con: str) -> bool:
    return (
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = 'public' AND t.relname = :t AND c.conname = :c"
            ),
            {"t": table, "c": con},
        ).scalar()
        is not None
    )


def _idx_exists(conn, idx: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:i"),
            {"i": idx},
        ).scalar()
        is not None
    )


def _rls_up(table: str) -> None:
    """Enable, force, and create the standard tenant-isolation policy."""
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY {table}_tenant_isolation ON "{table}" TO crm_app '
        f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
    )
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO crm_app')


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # integrations                                                       #
    # ------------------------------------------------------------------ #

    # 1. Drop the old 3-column unique; replace with two targeted uniques.
    if _con_exists(conn, "integrations", "uq_integrations_account"):
        op.drop_constraint("uq_integrations_account", "integrations", type_="unique")
    if not _con_exists(conn, "integrations", "uq_integrations_tenant_id_id"):
        op.create_unique_constraint(
            "uq_integrations_tenant_id_id", "integrations", ["tenant_id", "id"]
        )
    if not _con_exists(conn, "integrations", "uq_integrations_provider_account"):
        op.create_unique_constraint(
            "uq_integrations_provider_account",
            "integrations",
            ["provider", "provider_account_id"],
        )

    # 2. Rename check constraint.
    if _con_exists(conn, "integrations", "ck_integrations_status_valid"):
        op.execute('ALTER TABLE integrations DROP CONSTRAINT "ck_integrations_status_valid"')
    if not _con_exists(conn, "integrations", "ck_integrations_status"):
        op.execute(
            "ALTER TABLE integrations ADD CONSTRAINT ck_integrations_status "
            "CHECK (status IN ('active', 'disabled', 'error'))"
        )

    # 3. Rename encrypted_credentials → credentials_encrypted.
    if _col_exists(conn, "integrations", "encrypted_credentials") and not _col_exists(
        conn, "integrations", "credentials_encrypted"
    ):
        op.alter_column(
            "integrations",
            "encrypted_credentials",
            new_column_name="credentials_encrypted",
        )

    # 4. Add key_version.
    if not _col_exists(conn, "integrations", "key_version"):
        op.add_column(
            "integrations",
            sa.Column(
                "key_version",
                sa.SmallInteger(),
                nullable=False,
                server_default="1",
            ),
        )

    # 5. Migrate scopes JSONB → ARRAY(varchar).
    scopes_type = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='integrations' AND column_name='scopes'"
        )
    ).scalar()
    if scopes_type == "jsonb":
        op.add_column(
            "integrations",
            sa.Column("scopes_new", postgresql.ARRAY(sa.String()), nullable=True),
        )
        op.execute(
            """
            UPDATE integrations
            SET scopes_new = ARRAY(
                SELECT value
                FROM json_array_elements_text(scopes::json)
            )
            """
        )
        op.drop_column("integrations", "scopes")
        op.alter_column("integrations", "scopes_new", new_column_name="scopes", nullable=False)
        op.execute("ALTER TABLE integrations ALTER COLUMN scopes SET DEFAULT '{}' ")

    # 6. Tighten String lengths.
    op.alter_column(
        "integrations",
        "provider",
        existing_type=sa.String(50),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.alter_column(
        "integrations",
        "provider_account_id",
        existing_type=sa.String(200),
        type_=sa.String(128),
        existing_nullable=False,
    )
    op.alter_column(
        "integrations",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(16),
        existing_nullable=False,
    )

    # 7. Add query index.
    if not _idx_exists(conn, "ix_integrations_tenant_provider"):
        op.create_index(
            "ix_integrations_tenant_provider",
            "integrations",
            ["tenant_id", "provider"],
        )

    # ------------------------------------------------------------------ #
    # webhook_events                                                     #
    # ------------------------------------------------------------------ #

    # 1. Add integration_id column + FK.
    if not _col_exists(conn, "webhook_events", "integration_id"):
        op.add_column(
            "webhook_events",
            sa.Column("integration_id", sa.UUID(), nullable=True),
        )
        op.alter_column("webhook_events", "integration_id", nullable=False)

    if not _con_exists(conn, "webhook_events", "fk_webhook_events_tenant_integration"):
        op.create_foreign_key(
            "fk_webhook_events_tenant_integration",
            "webhook_events",
            "integrations",
            ["tenant_id", "integration_id"],
            ["tenant_id", "id"],
        )

    # 2. Add attempts column.
    if not _col_exists(conn, "webhook_events", "attempts"):
        op.add_column(
            "webhook_events",
            sa.Column(
                "attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    # 3. Drop signature_valid.
    if _col_exists(conn, "webhook_events", "signature_valid"):
        op.drop_column("webhook_events", "signature_valid")

    # 4. Make event_type NOT NULL and tighten.
    op.execute("UPDATE webhook_events SET event_type = 'unknown' WHERE event_type IS NULL")
    op.alter_column(
        "webhook_events",
        "event_type",
        existing_type=sa.String(100),
        type_=sa.String(32),
        nullable=False,
    )

    # 5. Replace status check.
    if _con_exists(conn, "webhook_events", "ck_webhook_events_status_valid"):
        op.execute('ALTER TABLE webhook_events DROP CONSTRAINT "ck_webhook_events_status_valid"')
    if not _con_exists(conn, "webhook_events", "ck_webhook_events_status"):
        op.execute(
            "ALTER TABLE webhook_events ADD CONSTRAINT ck_webhook_events_status "
            "CHECK (status IN ('received', 'processing', 'processed', 'failed', 'ignored'))"
        )

    # 6. Replace index.
    if _idx_exists(conn, "ix_webhook_events_tenant_received"):
        op.drop_index("ix_webhook_events_tenant_received", table_name="webhook_events")
    if not _idx_exists(conn, "ix_webhook_events_tenant_status"):
        op.create_index(
            "ix_webhook_events_tenant_status",
            "webhook_events",
            ["tenant_id", "status", "received_at"],
        )

    # 7. Tighten String lengths.
    op.alter_column(
        "webhook_events",
        "provider",
        existing_type=sa.String(50),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.alter_column(
        "webhook_events",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(16),
        existing_nullable=False,
    )

    # ------------------------------------------------------------------ #
    # conversations: external_contact_id                                 #
    # ------------------------------------------------------------------ #
    if not _col_exists(conn, "conversations", "external_contact_id"):
        op.add_column(
            "conversations",
            sa.Column("external_contact_id", sa.String(128), nullable=True),
        )

    # ------------------------------------------------------------------ #
    # RLS checks and policy enforcement                                  #
    # ------------------------------------------------------------------ #
    for table in ("integrations", "webhook_events"):
        row = conn.execute(
            sa.text(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = :t AND relnamespace = 'public'::regnamespace"
            ),
            {"t": table},
        ).one_or_none()
        if row and not (row.relrowsecurity and row.relforcerowsecurity):
            _rls_up(table)
        elif row:
            existing_policies = set(
                conn.execute(
                    sa.text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).scalars()
            )
            policy_name = f"{table}_tenant_isolation"
            if policy_name not in existing_policies:
                op.execute(
                    f'CREATE POLICY {policy_name} ON "{table}" TO crm_app '
                    f"USING (tenant_id = {GUC}) WITH CHECK (tenant_id = {GUC})"
                )
            op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO crm_app')

    missing = (
        conn.execute(
            sa.text(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN information_schema.columns col
                  ON col.table_schema = n.nspname AND col.table_name = c.relname
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND col.column_name = 'tenant_id'
                  AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
                """
            )
        )
        .scalars()
        .all()
    )
    EXEMPT = {"refresh_tokens"}
    missing = sorted(set(missing) - EXEMPT)
    if missing:
        raise RuntimeError(f"Tenant tables without RLS after migration: {missing}")


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # conversations                                                      #
    # ------------------------------------------------------------------ #
    if _col_exists(conn, "conversations", "external_contact_id"):
        op.drop_column("conversations", "external_contact_id")

    # ------------------------------------------------------------------ #
    # webhook_events                                                     #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "webhook_events",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "webhook_events",
        "provider",
        existing_type=sa.String(32),
        type_=sa.String(50),
        existing_nullable=False,
    )

    if _idx_exists(conn, "ix_webhook_events_tenant_status"):
        op.drop_index("ix_webhook_events_tenant_status", table_name="webhook_events")
    if not _idx_exists(conn, "ix_webhook_events_tenant_received"):
        op.create_index(
            "ix_webhook_events_tenant_received",
            "webhook_events",
            ["tenant_id", "received_at"],
        )

    if _con_exists(conn, "webhook_events", "ck_webhook_events_status"):
        op.execute('ALTER TABLE webhook_events DROP CONSTRAINT "ck_webhook_events_status"')
    if not _con_exists(conn, "webhook_events", "ck_webhook_events_status_valid"):
        op.execute(
            "ALTER TABLE webhook_events ADD CONSTRAINT ck_webhook_events_status_valid "
            "CHECK (status IN ('received', 'processed', 'failed', 'ignored'))"
        )

    op.alter_column(
        "webhook_events",
        "event_type",
        existing_type=sa.String(32),
        type_=sa.String(100),
        nullable=True,
    )

    if not _col_exists(conn, "webhook_events", "signature_valid"):
        op.add_column(
            "webhook_events",
            sa.Column("signature_valid", sa.Boolean(), nullable=True),
        )
        op.execute(
            "UPDATE webhook_events SET signature_valid = false WHERE signature_valid IS NULL"
        )
        op.alter_column("webhook_events", "signature_valid", nullable=False)

    if _col_exists(conn, "webhook_events", "attempts"):
        op.drop_column("webhook_events", "attempts")

    if _con_exists(conn, "webhook_events", "fk_webhook_events_tenant_integration"):
        op.drop_constraint(
            "fk_webhook_events_tenant_integration", "webhook_events", type_="foreignkey"
        )
    if _col_exists(conn, "webhook_events", "integration_id"):
        op.drop_column("webhook_events", "integration_id")

    # ------------------------------------------------------------------ #
    # integrations                                                       #
    # ------------------------------------------------------------------ #
    if _idx_exists(conn, "ix_integrations_tenant_provider"):
        op.drop_index("ix_integrations_tenant_provider", table_name="integrations")

    op.alter_column(
        "integrations",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "integrations",
        "provider_account_id",
        existing_type=sa.String(128),
        type_=sa.String(200),
        existing_nullable=False,
    )
    op.alter_column(
        "integrations",
        "provider",
        existing_type=sa.String(32),
        type_=sa.String(50),
        existing_nullable=False,
    )

    scopes_type = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='integrations' AND column_name='scopes'"
        )
    ).scalar()
    if scopes_type == "ARRAY":
        op.add_column(
            "integrations",
            sa.Column(
                "scopes_old",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
        op.execute("UPDATE integrations SET scopes_old = to_jsonb(scopes)")
        op.drop_column("integrations", "scopes")
        op.alter_column("integrations", "scopes_old", new_column_name="scopes", nullable=False)
        op.execute("ALTER TABLE integrations ALTER COLUMN scopes SET DEFAULT '[]'::jsonb")

    if _col_exists(conn, "integrations", "key_version"):
        op.drop_column("integrations", "key_version")

    if _col_exists(conn, "integrations", "credentials_encrypted") and not _col_exists(
        conn, "integrations", "encrypted_credentials"
    ):
        op.alter_column(
            "integrations",
            "credentials_encrypted",
            new_column_name="encrypted_credentials",
        )

    if _con_exists(conn, "integrations", "ck_integrations_status"):
        op.execute('ALTER TABLE integrations DROP CONSTRAINT "ck_integrations_status"')
    if not _con_exists(conn, "integrations", "ck_integrations_status_valid"):
        op.execute(
            "ALTER TABLE integrations ADD CONSTRAINT ck_integrations_status_valid "
            "CHECK (status IN ('active', 'disabled', 'error'))"
        )

    if _con_exists(conn, "integrations", "uq_integrations_provider_account"):
        op.drop_constraint("uq_integrations_provider_account", "integrations", type_="unique")
    if _con_exists(conn, "integrations", "uq_integrations_tenant_id_id"):
        op.drop_constraint("uq_integrations_tenant_id_id", "integrations", type_="unique")
    if not _con_exists(conn, "integrations", "uq_integrations_account"):
        op.create_unique_constraint(
            "uq_integrations_account",
            "integrations",
            ["tenant_id", "provider", "provider_account_id"],
        )
