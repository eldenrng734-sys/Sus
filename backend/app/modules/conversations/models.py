import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class Conversation(UUIDPkMixin, TimestampMixin, Base):
    """A chat thread on WhatsApp / Messenger."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id_id"),
        CheckConstraint("channel IN ('whatsapp','messenger','email','web')", name="channel"),
        CheckConstraint("status IN ('open','pending','closed')", name="status"),
        # A member of the SAME tenant only
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        # Provider thread IDs are unique per tenant and channel (when present)
        Index(
            "conversations_tenant_channel_external_uq",
            "tenant_id",
            "channel",
            "external_conversation_id",
            unique=True,
            postgresql_where=text("external_conversation_id IS NOT NULL"),
        ),
        Index(
            "ix_conversations_tenant_status_last_msg",
            "tenant_id",
            "status",
            "last_message_at",
        ),
        Index(
            "ix_conversations_tenant_assignee_last_msg",
            "tenant_id",
            "assigned_user_id",
            "last_message_at",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    # TODO: add composite FK (tenant_id, lead_id) -> leads once Dev 3's table is merged
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    external_conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Used for the WhatsApp 24-hour reply window rule
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(UUIDPkMixin, TimestampMixin, Base):
    """One message inside a conversation. message_text is PII: never log it."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_messages_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "provider_message_id",
            name="uq_messages_tenant_provider_message_id",
        ),
        CheckConstraint("provider IN ('whatsapp','messenger')", name="provider"),
        CheckConstraint("direction IN ('inbound','outbound')", name="direction"),
        CheckConstraint(
            "status IN ('received','queued','sent','delivered','read','failed')",
            name="status",
        ),
        # A message can only point to a conversation of the SAME tenant
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_messages_tenant_conversation_created",
            "tenant_id",
            "conversation_id",
            "created_at",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'received'")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
