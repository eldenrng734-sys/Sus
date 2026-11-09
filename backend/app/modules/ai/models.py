import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPkMixin


class LeadAssessment(UUIDPkMixin, Base):
    """One validated AI assessment per run. The AI advises; our code decides."""

    __tablename__ = "lead_assessments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            "category IS NULL OR category IN "
            "('business_customer','individual','partner','spam','unknown')",
            name="category",
        ),
        CheckConstraint(
            "intent IS NULL OR intent IN "
            "('request_demo','pricing','support','info','complaint','other','unknown')",
            name="intent",
        ),
        CheckConstraint(
            "buying_stage IS NULL OR buying_stage IN "
            "('awareness','consideration','decision','unknown')",
            name="buying_stage",
        ),
        CheckConstraint("priority IS NULL OR priority IN ('low','medium','high')", name="priority"),
        CheckConstraint(
            "recommended_action IS NULL OR recommended_action IN "
            "('call','schedule_demo','email','follow_up','support','none')",
            name="recommended_action",
        ),
        CheckConstraint(
            "follow_up_days IS NULL OR follow_up_days BETWEEN 0 AND 365",
            name="follow_up_days",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence"),
        CheckConstraint("lead_score BETWEEN 0 AND 100", name="lead_score"),
        CheckConstraint(
            "sentiment IS NULL OR sentiment IN ('positive','neutral','negative')",
            name="sentiment",
        ),
        CheckConstraint("status IN ('ok','fallback','failed')", name="status"),
        CheckConstraint(
            "review_status IN ('not_required','pending','approved','rejected')",
            name="review_status",
        ),
        CheckConstraint(
            "needs_human_review = false OR review_status <> 'not_required'",
            name="review_required_has_status",
        ),
        CheckConstraint(
            "review_status NOT IN ('approved','rejected') "
            "OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="reviewed_has_reviewer",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewed_by_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_lead_assessments_tenant_lead_created",
            "tenant_id",
            "lead_id",
            "created_at",
        ),
        Index(
            "ix_lead_assessments_tenant_review_queue",
            "tenant_id",
            "needs_human_review",
            "created_at",
            postgresql_where=text("needs_human_review"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    # TODO: add composite FK (tenant_id, lead_id) -> leads once Dev 3's table is merged
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest: Mapped[str | None] = mapped_column(Text, nullable=True)
    buying_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)

    needs_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'not_required'")
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # Validated JSON only, no unredacted PII
    raw_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ok'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
