import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class EventName(str, Enum):
    LEAD_CREATED = "lead.created"
    MESSAGE_RECEIVED = "message.received"


class _EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: uuid.UUID
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class LeadCreatedPayload(_EventPayload):
    lead_id: uuid.UUID


class MessageReceivedPayload(_EventPayload):
    message_id: str = Field(min_length=1, max_length=255)
    provider: Literal["whatsapp", "meta"]


_Payload = LeadCreatedPayload | MessageReceivedPayload
_PayloadInput = Mapping[str, object] | BaseModel
_Handler = Callable[["DomainEvent"], None]


@dataclass(frozen=True)
class DomainEvent:
    name: EventName
    payload: _Payload


class UnknownEventError(ValueError):
    """The emitter was asked to publish or register an unsupported event name."""


class EventPayloadError(ValueError):
    """The payload does not satisfy the selected event's contract."""


class EventHandlerError(RuntimeError):
    """A registered event handler failed during synchronous dispatch."""


class EventEmitter:
    """Synchronous in-process event dispatcher with validated payload contracts."""

    def __init__(self) -> None:
        self._handlers: dict[EventName, list[_Handler]] = {
            event_name: [] for event_name in EventName
        }

    def register(self, event_name: str | EventName, handler: _Handler) -> None:
        name = self._event_name(event_name)
        if handler not in self._handlers[name]:
            self._handlers[name].append(handler)

    def publish(self, event_name: str | EventName, payload: _PayloadInput) -> None:
        name = self._event_name(event_name)
        if isinstance(payload, BaseModel):
            payload = payload.model_dump()

        try:
            if name is EventName.LEAD_CREATED:
                validated_payload: _Payload = LeadCreatedPayload.model_validate(payload)
            else:
                validated_payload = MessageReceivedPayload.model_validate(payload)
        except (TypeError, ValidationError) as exc:
            raise EventPayloadError(f"Invalid payload for {name.value}") from exc

        event = DomainEvent(name=name, payload=validated_payload)
        for handler in tuple(self._handlers[name]):
            try:
                handler(event)
            except Exception as exc:
                raise EventHandlerError(f"Handler failed for {name.value}") from exc

    @staticmethod
    def _event_name(event_name: str | EventName) -> EventName:
        try:
            return EventName(event_name)
        except (TypeError, ValueError) as exc:
            raise UnknownEventError("Unknown event name") from exc


event_emitter = EventEmitter()
