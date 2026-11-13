import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class Lead(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    company_name: Mapped[str | None] = mapped_column(String(200))

    source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'manual'")
    )
    source_campaign: Mapped[str | None] = mapped_column(String(200))
    external_id: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    lost_reason: Mapped[str | None] = mapped_column(Text)

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    intent: Mapped[str | None] = mapped_column(String(50))
    lead_score: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'medium'")
    )

    consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_source: Mapped[str | None] = mapped_column(String(20))
    opted_out: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opted_out_source: Mapped[str | None] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_leads_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_leads_assigned_member",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            name="fk_leads_team",
        ),
        CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'proposal', 'won', 'lost')",
            name="status_valid",
        ),
        CheckConstraint(
            (
                "source IN ('website_form','tracking','whatsapp','facebook_lead_ads',"
                "'messenger','manual','csv')"
            ),
            name="source_valid",
        ),
        CheckConstraint(
            (
                "lost_reason IS NULL OR lost_reason IN "
                "('price','timing','no_response','competitor','not_qualified','other')"
            ),
            name="lost_reason_valid",
        ),
        CheckConstraint("status <> 'lost' OR lost_reason IS NOT NULL", name="lost_reason_required"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="priority_valid"),
        CheckConstraint(
            "lead_score IS NULL OR (lead_score BETWEEN 0 AND 100)",
            name="score_range",
        ),
        CheckConstraint("email IS NULL OR email = lower(email)", name="email_lowercase"),
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="contact_required"),
        CheckConstraint(
            "NOT opted_out OR opted_out_at IS NOT NULL",
            name="opted_out_timestamp_required",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            (
                "consent_source IS NULL OR consent_source IN "
                "('web_form','whatsapp','manual','import','api')"
            ),
            name="consent_source_valid",
        ),
        Index(
            "uq_leads_tenant_source_external",
            "tenant_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index("ix_leads_tenant_created", "tenant_id", "created_at"),
        Index("ix_leads_tenant_assigned", "tenant_id", "assigned_user_id"),
        Index("ix_leads_tenant_status", "tenant_id", "status"),
        Index("ix_leads_tenant_email", "tenant_id", "email"),
        Index("ix_leads_tenant_phone", "tenant_id", "phone"),
        Index("ix_leads_tenant_team", "tenant_id", "team_id"),
        Index("ix_leads_tenant_priority", "tenant_id", "priority"),
    )


class AssignmentCursor(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "assignment_cursors"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    last_assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "team_id", name="uq_assignment_cursors_tenant_team"),
        ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            name="fk_assignment_cursors_team",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "last_assigned_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_assignment_cursors_last_assigned_member",
            ondelete="RESTRICT",
        ),
    )


class Contact(UUIDPkMixin, TimestampMixin, Base):
    """Customer record after a lead is converted."""

    __tablename__ = "contacts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    company_name: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_contacts_tenant_id_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["leads.tenant_id", "leads.id"],
            name="fk_contacts_lead",
        ),
        Index("ix_contacts_tenant_created", "tenant_id", "created_at"),
    )


class Interaction(UUIDPkMixin, TimestampMixin, Base):
    """Website activity, form submissions, calls and events."""

    __tablename__ = "interactions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False)

    source: Mapped[str | None] = mapped_column(String(50))

    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["leads.tenant_id", "leads.id"],
            name="fk_interactions_lead",
        ),
        Index(
            "ix_interactions_tenant_lead_time",
            "tenant_id",
            "lead_id",
            "occurred_at",
        ),
    )
