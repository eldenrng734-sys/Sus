import uuid
from datetime import datetime, time

from sqlalchemy import DateTime, ForeignKey, String, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'Asia/Dhaka'"),
    )
    quiet_hours_start: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        server_default=text("'21:00:00'::time"),
    )
    quiet_hours_end: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        server_default=text("'09:00:00'::time"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
