import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPkMixin


class OutboxEvent(UUIDPkMixin, Base):
    __tablename__ = "outbox_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
            name="outbox_events_tenant_id_fkey",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="outbox_events_tenant_id_id_uq"),
        CheckConstraint(
            "status IN ('pending','processing','processed','failed','dead')",
            name="status",
        ),
        CheckConstraint(
            "aggregate_type IN ('lead','conversation','message','task','assessment','integration')",
            name="aggregate_type",
        ),
        Index(
            "outbox_tenant_idempotency_uq",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_outbox_events_status_available", "status", "available_at"),
        Index(
            "ix_outbox_events_tenant_created",
            "tenant_id",
            desc("created_at"),
        ),
    )
