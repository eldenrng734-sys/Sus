import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskType = Literal["call", "meeting", "reminder", "follow_up", "other"]
TaskStatus = Literal["open", "done", "cancelled"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    type: TaskType = "other"
    due_at: datetime | None = None
    lead_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None
    status: TaskStatus | None = None
    assigned_user_id: uuid.UUID | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    type: str
    status: str
    due_at: datetime | None
    completed_at: datetime | None
    lead_id: uuid.UUID | None
    assigned_user_id: uuid.UUID
    created_at: datetime
