
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPkMixin


class AuthAttempt(UUIDPkMixin, Base):
    """Global login-attempt records; intentionally has no tenant_id or tenant RLS."""

    __tablename__ = "auth_attempts"

    email: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        Index("ix_auth_attempts_email_created", "email", "created_at"),
        Index("ix_auth_attempts_ip_created", "ip_address", "created_at"),
    )
