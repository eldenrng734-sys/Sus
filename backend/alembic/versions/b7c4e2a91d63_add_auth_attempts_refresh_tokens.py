"""Add auth attempts, refresh tokens and audit fields."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b7c4e2a91d63"
down_revision = "f9f7fcdf9d79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Complete the existing audit_logs schema.
    op.add_column(
        "audit_logs",
        sa.Column(
            "actor_type",
            sa.String(length=30),
            server_default=sa.text("'user'"),
            nullable=False,
        ),
    )
    op.add_column(
        "audit_logs",
        sa.Column("request_id", sa.String(length=100), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_audit_logs_valid_actor_type"),
        "audit_logs",
        "actor_type IN ('user', 'system', 'automation', 'platform_admin')",
    )

    # Store login attempts for rate limiting.
    op.create_table(
        "auth_attempts",
        sa.Column(
            "email",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email = lower(email)",
            name=op.f("ck_auth_attempts_email_lowercase"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_attempts")),
    )
    op.create_index(
        "ix_auth_attempts_email_created",
        "auth_attempts",
        ["email", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_attempts_ip_created",
        "auth_attempts",
        ["ip_address", "created_at"],
        unique=False,
    )

    # Store hashed refresh tokens and rotation families.
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_refresh_tokens_token_hash"),
        ),
    )
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_family_id",
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_auth_attempts_ip_created", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_email_created", table_name="auth_attempts")
    op.drop_table("auth_attempts")

    op.drop_constraint(
        op.f("ck_audit_logs_valid_actor_type"),
        "audit_logs",
        type_="check",
    )
    op.drop_column("audit_logs", "request_id")
    op.drop_column("audit_logs", "actor_type")
