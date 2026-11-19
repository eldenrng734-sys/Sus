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
    lead_name: str | None = None
    lead_phone: str | None = None
    lead_opted_out: bool | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    provider: str
    provider_message_id: str | None
    direction: str
    message_text: str | None
    status: str
    error_code: str | None
    idempotency_key: str | None
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


class ConversationAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str | None
    sentiment: str | None
    confidence: float | None
    needs_human_review: bool
    status: Literal["ok", "fallback", "failed"]
    model: str
    prompt_version: str
    created_at: datetime
