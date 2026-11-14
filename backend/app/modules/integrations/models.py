import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class Integration(UUIDPkMixin, TimestampMixin, Base):
    """A connected external account such as WhatsApp or Meta.

    One provider account (phone number / page) belongs to exactly one company —
    enforced by the global unique on (provider, provider_account_id).
    The composite unique on (tenant_id, id) exists so that webhook_events can
    reference it via a composite FK.
    """

    __tablename__ = "integrations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # whatsapp → phone_number_id, facebook_page → page_id
    provider_account_id: Mapped[str] = mapped_column(String(128), nullable=False)

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # OAuth scopes granted by the provider account owner
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("'{}'"),
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    # nonce + ciphertext — never log or return this field
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # bumped each time the encryption key is rotated
    key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # composite FK target — webhook_events.integration_id references this
        UniqueConstraint("tenant_id", "id", name="uq_integrations_tenant_id_id"),
        # global: one WhatsApp number / FB page belongs to exactly one company
        UniqueConstraint(
            "provider", "provider_account_id", name="uq_integrations_provider_account"
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'error')",
            name="ck_integrations_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_integrations_tenant_id_tenants",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "owner_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_integrations_owner",
        ),
        Index("ix_integrations_tenant_provider", "tenant_id", "provider"),
    )


class WebhookEvent(UUIDPkMixin, Base):
    """Incoming webhook event with dedup and audit trail.

    record_event() inserts with ON CONFLICT DO NOTHING — a None return
    means the event was already processed and the caller should stop.

    tenant_id is NOT NULL: the framework resolves the tenant from the
    integration before writing anything. Events with unknown accounts or
    bad signatures are rejected at the HTTP layer and never stored.

    For WhatsApp status callbacks build event_id as f"{wamid}:{status}"
    so sent / delivered / read each produce a distinct row.

    payload contains PII (phone numbers, message text). Add a retention
    purge job before going to production.
    """

    __tablename__ = "webhook_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    integration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    # wamid / leadgen_id / mid — unique within a provider per tenant
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # message | status | leadgen
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="received")

    # incremented each time the worker retries processing
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # short description of the last error — no PII
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # contains PII — never log this field
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # THE dedup guarantee: same provider event arriving twice → one row
        UniqueConstraint("tenant_id", "provider", "event_id", name="uq_webhook_events_dedup"),
        CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'failed', 'ignored')",
            name="ck_webhook_events_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_webhook_events_tenant_id_tenants",
        ),
        # composite FK — ensures integration belongs to the same tenant
        ForeignKeyConstraint(
            ["tenant_id", "integration_id"],
            ["integrations.tenant_id", "integrations.id"],
            name="fk_webhook_events_tenant_integration",
        ),
        Index("ix_webhook_events_tenant_status", "tenant_id", "status", "received_at"),
    )


def record_event(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    integration_id: uuid.UUID,
    provider: str,
    event_id: str,
    event_type: str,
    payload: dict,
) -> uuid.UUID | None:
    """Record an incoming webhook event with deduplication guarantee.

    Uses PostgreSQL INSERT ... ON CONFLICT (tenant_id, provider, event_id) DO NOTHING.
    Returns the created WebhookEvent id, or None if the event was already recorded (duplicate).
    """
    stmt = (
        insert(WebhookEvent)
        .values(
            tenant_id=tenant_id,
            integration_id=integration_id,
            provider=provider,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_webhook_events_dedup")
        .returning(WebhookEvent.id)
    )
    return session.execute(stmt).scalar_one_or_none()

