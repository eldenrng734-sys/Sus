import uuid
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
