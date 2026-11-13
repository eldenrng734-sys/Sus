"""Add lead concurrency/audit fields and tenant-scoped idempotency storage.

Revision ID: e3a2b7c9d140
Revises: a6cbbf5ec79e
Create Date: 2026-11-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3a2b7c9d140"
down_revision: Union[str, Sequence[str], None] = "a6cbbf5ec79e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    # Repair legacy lead rows before tightening the fields required by the API.
    op.execute(
        """
        UPDATE leads
        SET name = COALESCE(
            NULLIF(BTRIM(name), ''), NULLIF(email, ''), NULLIF(phone, ''), 'Unknown lead'
        )
        WHERE name IS NULL OR BTRIM(name) = ''
        """
    )
    op.execute("UPDATE leads SET email = LOWER(BTRIM(email)) WHERE email IS NOT NULL")
    op.execute(
        """
        UPDATE leads SET priority = 'medium'
        WHERE priority IS NULL OR priority NOT IN ('low', 'medium', 'high')
        """
    )
    op.execute(
        """
        UPDATE leads SET source = 'manual'
        WHERE source NOT IN (
            'website_form','tracking','whatsapp','facebook_lead_ads','messenger','manual','csv'
        )
        """
    )
    op.execute(
        """
        UPDATE leads SET lost_reason = 'other'
        WHERE status = 'lost'
          AND (lost_reason IS NULL OR lost_reason NOT IN
            ('price','timing','no_response','competitor','not_qualified','other'))
        """
    )
    op.execute(
        """
        UPDATE leads SET lost_reason = NULL
        WHERE status <> 'lost'
          AND lost_reason IS NOT NULL
          AND lost_reason NOT IN
            ('price','timing','no_response','competitor','not_qualified','other')
        """
    )

    op.alter_column(
        "leads",
        "source",
        existing_type=sa.String(length=50),
        server_default=sa.text("'manual'"),
        nullable=False,
    )
    op.alter_column("leads", "name", existing_type=sa.String(length=200), nullable=False)
    op.alter_column(
        "leads",
        "priority",
        existing_type=sa.String(length=10),
        server_default=sa.text("'medium'"),
        nullable=False,
    )
    op.add_column(
        "leads",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_index(
        "ix_leads_tenant_team", "leads", ["tenant_id", "team_id"], unique=False
    )
    op.create_index(
        "ix_leads_tenant_priority", "leads", ["tenant_id", "priority"], unique=False
    )
    op.add_column("leads", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("consent_source", sa.String(length=20), nullable=True))
    op.add_column("leads", sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        "ck_leads_source_valid",
        "leads",
        (
            "source IN ('website_form','tracking','whatsapp','facebook_lead_ads',"
            "'messenger','manual','csv')"
        ),
    )
    op.create_check_constraint(
        "ck_leads_lost_reason_valid",
        "leads",
        (
            "lost_reason IS NULL OR lost_reason IN "
            "('price','timing','no_response','competitor','not_qualified','other')"
        ),
    )
    op.create_check_constraint(
        "ck_leads_lost_reason_required",
        "leads",
        "status <> 'lost' OR lost_reason IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_leads_email_lowercase",
        "leads",
        "email IS NULL OR email = LOWER(email)",
    )
    op.create_check_constraint(
        "ck_leads_contact_required",
        "leads",
        "email IS NOT NULL OR phone IS NOT NULL",
    )
    op.create_check_constraint("ck_leads_version_positive", "leads", "version >= 1")
    op.create_check_constraint(
        "ck_leads_consent_source_valid",
        "leads",
        (
            "consent_source IS NULL OR consent_source IN "
            "('web_form','whatsapp','manual','import','api')"
        ),
    )

    op.add_column(
        "interactions",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_interactions_created_by_user_id_users",
        "interactions",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("caller_type", sa.String(length=20), nullable=False),
        sa.Column("caller_id", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "caller_type IN ('user','service')",
            name="ck_idempotency_keys_caller_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_idempotency_keys_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_keys"),
        sa.UniqueConstraint(
            "tenant_id",
            "caller_type",
            "caller_id",
            "method",
            "path",
            "key",
            name="uq_idempotency_keys_scope",
        ),
    )
    op.create_index(
        "ix_idempotency_keys_expires_at",
        "idempotency_keys",
        ["expires_at"],
        unique=False,
    )
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON "idempotency_keys" TO crm_app')
    op.execute('ALTER TABLE "idempotency_keys" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "idempotency_keys" FORCE ROW LEVEL SECURITY')
    op.execute(
        "CREATE POLICY idempotency_keys_tenant_isolation ON idempotency_keys TO crm_app "
        f"USING (tenant_id = {TENANT_GUC}) WITH CHECK (tenant_id = {TENANT_GUC})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS idempotency_keys_tenant_isolation ON idempotency_keys")
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_constraint(
        "fk_interactions_created_by_user_id_users",
        "interactions",
        type_="foreignkey",
    )
    op.drop_column("interactions", "created_by_user_id")

    op.drop_constraint("ck_leads_consent_source_valid", "leads", type_="check")
    op.drop_constraint("ck_leads_version_positive", "leads", type_="check")
    op.drop_constraint("ck_leads_contact_required", "leads", type_="check")
    op.drop_constraint("ck_leads_email_lowercase", "leads", type_="check")
    op.drop_constraint("ck_leads_lost_reason_required", "leads", type_="check")
    op.drop_constraint("ck_leads_lost_reason_valid", "leads", type_="check")
    op.drop_constraint("ck_leads_source_valid", "leads", type_="check")

    op.drop_column("leads", "opted_out_at")
    op.drop_column("leads", "consent_source")
    op.drop_column("leads", "consent_at")
    op.drop_index("ix_leads_tenant_priority", table_name="leads")
    op.drop_index("ix_leads_tenant_team", table_name="leads")
    op.drop_column("leads", "version")
    op.alter_column(
        "leads",
        "priority",
        existing_type=sa.String(length=10),
        server_default=None,
        nullable=True,
    )
    op.alter_column(
        "leads",
        "source",
        existing_type=sa.String(length=50),
        server_default=None,
        nullable=False,
    )
    op.alter_column("leads", "name", existing_type=sa.String(length=200), nullable=True)
