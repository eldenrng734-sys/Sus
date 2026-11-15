import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPkMixin


class Notification(UUIDPkMixin, Base):
    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[Literal["new_lead"]] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    entity_type: Mapped[Literal["lead"]] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_notifications_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_notifications_recipient_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint("type IN ('new_lead')", name="type_valid"),
        CheckConstraint("entity_type IN ('lead')", name="entity_type_valid"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(btrim(body)) > 0", name="body_not_blank"),
        Index(
            "ix_notifications_tenant_user_created",
            "tenant_id",
            "user_id",
            "created_at",
        ),
    )
