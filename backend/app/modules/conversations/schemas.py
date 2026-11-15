import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    lead_id: uuid.UUID
    channel: Literal["whatsapp", "messenger", "email", "web"]
    external_conversation_id: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    channel: str
    status: str
    assigned_user_id: uuid.UUID | None
    last_message_at: datetime | None
    last_inbound_at: datetime | None
    created_at: datetime


class ConversationAnalysisOut(BaseModel):
    summary: str
    sentiment: Literal["positive", "neutral", "negative"]
    confidence: float | None
    needs_human_review: bool
    status: str
    model: str
    prompt_version: str
    created_at: datetime


class MessageCreate(BaseModel):
    conversation_id: uuid.UUID
    message_text: str = Field(min_length=1, max_length=4096)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    message_text: str | None
    status: str
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None


class TimelineEvent(BaseModel):
    kind: Literal["interaction", "message"]
    type: str
    at: datetime
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
