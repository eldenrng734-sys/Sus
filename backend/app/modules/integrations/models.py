import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class Integration(UUIDPkMixin, TimestampMixin, Base):
    """A connected external account such as WhatsApp or Meta."""

    __tablename__ = "integrations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    provider_account_id: Mapped[str] = mapped_column(String(200), nullable=False)

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    scopes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    encrypted_credentials: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "provider_account_id",
            name="uq_integrations_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "owner_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_integrations_owner",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'error')",
            name="status_valid",
        ),
    )


class WebhookEvent(UUIDPkMixin, Base):
    """Incoming webhook events with duplicate protection."""

    __tablename__ = "webhook_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    event_id: Mapped[str] = mapped_column(String(255), nullable=False)

    event_type: Mapped[str | None] = mapped_column(String(100))

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="received")

    error: Mapped[str | None] = mapped_column(Text)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "event_id",
            name="uq_webhook_events_dedup",
        ),
        CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'ignored')",
            name="status_valid",
        ),
        Index(
            "ix_webhook_events_tenant_received",
            "tenant_id",
            "received_at",
        ),
    )
