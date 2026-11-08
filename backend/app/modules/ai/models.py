import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class LeadAssessment(UUIDPkMixin, TimestampMixin, Base):
    """The AI's opinion about a lead. The AI only advises; our code decides."""

    __tablename__ = "lead_assessments"
    __table_args__ = (
        Index("ix_lead_assessments_tenant_created", "tenant_id", "created_at"),
        Index("ix_lead_assessments_tenant_lead", "tenant_id", "lead_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # The leads table is built by Dev 3. The foreign key is added after it exists.
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    category: Mapped[str] = mapped_column(String(50), nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    interest: Mapped[str | None] = mapped_column(String(200), nullable=True)
    buying_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    lead_score: Mapped[int] = mapped_column(Integer, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(50), nullable=False)
    follow_up_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
