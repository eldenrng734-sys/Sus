import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskType = Literal["call", "meeting", "reminder", "follow_up"]
TaskStatus = Literal["open", "done", "cancelled", "paused"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    type: TaskType
    due_at: datetime
    lead_id: uuid.UUID
    assigned_user_id: uuid.UUID | None = None
    requires_approval: bool = False

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone")
        return value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    status: TaskStatus | None = None
    assigned_user_id: uuid.UUID | None = None
    version: int | None = Field(
        default=None,
        description="Current task version for optimistic locking; send to detect conflicts",
    )

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_at must include a timezone")
        return value


class TaskApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    lead_id: uuid.UUID
    title: str
    notes: str | None
    type: str
    status: str
    due_at: datetime
    assigned_user_id: uuid.UUID | None
    team_id: uuid.UUID | None
    requires_approval: bool
    approval_status: str
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    approval_note: str | None
    rejected_by_user_id: uuid.UUID | None
    rejected_at: datetime | None
    completed_at: datetime | None
    created_by: str
    version: int
    created_at: datetime
    updated_at: datetime
