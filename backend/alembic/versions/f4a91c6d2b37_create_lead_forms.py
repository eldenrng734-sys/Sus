"""Create tenant-scoped public lead forms."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f4a91c6d2b37"
down_revision: Union[str, None] = "e3a2b7c9d140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_forms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "allowed_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("consent_text", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_lead_forms_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(allowed_fields) = 'array'",
            name="ck_lead_forms_allowed_fields_array",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lead_forms"),
        sa.UniqueConstraint("public_id", name="uq_lead_forms_public_id"),
    )
    op.create_index("ix_lead_forms_tenant_id", "lead_forms", ["tenant_id"])

    op.execute("ALTER TABLE lead_forms ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_forms FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT ON lead_forms TO crm_app")
    op.execute(
        """
        CREATE POLICY lead_forms_public_lookup
        ON lead_forms
        FOR SELECT
        TO crm_app
        USING (
            is_active
            AND public_id = NULLIF(current_setting('app.public_form_id', true), '')
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS lead_forms_public_lookup ON lead_forms")
    op.drop_index("ix_lead_forms_tenant_id", table_name="lead_forms")
    op.drop_table("lead_forms")
