import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReviewStatus = Literal["not_required", "pending", "approved", "rejected"]


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    conversation_id: uuid.UUID | None
    category: str | None
    intent: str | None
    interest: str | None
    buying_stage: str | None
    sentiment: str | None
    priority: str | None
    lead_score: int | None
    recommended_action: str | None
    follow_up_days: int | None
    confidence: float | None
    needs_human_review: bool
    review_status: ReviewStatus
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    summary: str | None
    model: str
    prompt_version: str
    status: Literal["ok", "fallback", "failed"]
    created_at: datetime


class AssessmentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal["approved", "rejected"]
    review_note: str | None = Field(default=None, max_length=2000)

    @field_validator("review_note")
    @classmethod
    def _normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
