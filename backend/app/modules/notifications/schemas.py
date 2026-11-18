import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    type: Literal["new_lead"]
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    entity_type: Literal["lead"]
    entity_id: uuid.UUID

    @field_validator("title", "body", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    body: str
    entity_type: str
    entity_id: uuid.UUID
    read_at: datetime | None = None
    created_at: datetime


class NotificationMeta(BaseModel):
    unread_count: int


class NotificationListResponse(BaseModel):
    data: list[NotificationOut]
    meta: NotificationMeta
