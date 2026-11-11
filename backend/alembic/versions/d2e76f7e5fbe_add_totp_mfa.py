"""add_totp_mfa

Revision ID: d2e76f7e5fbe
Revises: c3a8d5e17f42
Create Date: 2026-11-10 08:24:24.090156

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2e76f7e5fbe'
down_revision: Union[str, Sequence[str], None] = 'c3a8d5e17f42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("mfa_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("mfa_last_used_step", sa.Integer(), nullable=True))
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_mfa_recovery_codes_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_recovery_codes")),
    )
    op.create_index(
        "ix_mfa_recovery_codes_user_id",
        "mfa_recovery_codes",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "mfa_login_challenges",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
            "purpose IN ('login','enrollment')",
            name=op.f("ck_mfa_login_challenges_purpose_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mfa_login_challenges_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_login_challenges")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_mfa_login_challenges_token_hash")),
    )
    op.create_index(
        "ix_mfa_login_challenges_user_id",
        "mfa_login_challenges",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_mfa_login_challenges_expires_at",
        "mfa_login_challenges",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mfa_login_challenges_expires_at", table_name="mfa_login_challenges")
    op.drop_index("ix_mfa_login_challenges_user_id", table_name="mfa_login_challenges")
    op.drop_table("mfa_login_challenges")
    op.drop_index("ix_mfa_recovery_codes_user_id", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_column("users", "mfa_last_used_step")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("refresh_tokens", "mfa_verified")
