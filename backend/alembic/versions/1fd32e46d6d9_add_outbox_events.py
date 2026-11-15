"""add outbox_events

Revision ID: 1fd32e46d6d9
Revises: f6a8c0d2e491
Create Date: 2026-11-15 09:59:23.286246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1fd32e46d6d9'
down_revision: Union[str, Sequence[str], None] = 'f6a8c0d2e491'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE outbox_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE RESTRICT,
            event_type text NOT NULL,
            aggregate_type text NOT NULL,
            aggregate_id uuid NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key text,
            status text NOT NULL DEFAULT 'pending',
            attempts smallint NOT NULL DEFAULT 0,
            available_at timestamptz NOT NULL DEFAULT now(),
            locked_at timestamptz,
            locked_by text,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            processed_at timestamptz,
            CONSTRAINT outbox_events_tenant_id_id_uq UNIQUE (tenant_id, id),
            CONSTRAINT ck_outbox_events_status
                CHECK (status IN ('pending','processing','processed','failed','dead')),
            CONSTRAINT ck_outbox_events_aggregate_type
                CHECK (aggregate_type IN
                    ('lead','conversation','message','task','assessment','integration'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX outbox_tenant_idempotency_uq
            ON outbox_events (tenant_id, idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute("CREATE INDEX ix_outbox_events_status_available ON outbox_events (status, available_at)")
    op.execute("CREATE INDEX ix_outbox_events_tenant_created ON outbox_events (tenant_id, created_at DESC)")

    op.execute("ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY outbox_events_tenant_isolation ON outbox_events
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_worker') THEN
                CREATE POLICY outbox_worker_claim ON outbox_events
                    FOR ALL TO crm_worker USING (true) WITH CHECK (true);
                GRANT SELECT, UPDATE ON outbox_events TO crm_worker;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
                GRANT SELECT, INSERT ON outbox_events TO crm_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outbox_events")
