import uuid
from datetime import UTC, datetime

import pytest

from app.core.events import (
    DomainEvent,
    EventEmitter,
    EventHandlerError,
    EventName,
    EventPayloadError,
    LeadCreatedPayload,
    MessageReceivedPayload,
    UnknownEventError,
)


def _lead_payload() -> dict:
    return {
        "tenant_id": uuid.uuid4(),
        "lead_id": uuid.uuid4(),
        "occurred_at": datetime.now(UTC),
    }


def test_emitter_initializes_with_no_handlers_and_missing_handlers_are_safe():
    emitter = EventEmitter()

    emitter.publish(EventName.LEAD_CREATED, _lead_payload())


def test_lead_created_payload_is_validated_and_handlers_run_once():
    emitter = EventEmitter()
    received: list[DomainEvent] = []
    handler = received.append
    emitter.register(EventName.LEAD_CREATED, handler)
    emitter.register(EventName.LEAD_CREATED, handler)
    payload = _lead_payload()

    emitter.publish(EventName.LEAD_CREATED, payload)

    assert len(received) == 1
    assert received[0].name is EventName.LEAD_CREATED
    assert received[0].payload == LeadCreatedPayload.model_validate(payload)


def test_message_received_payload_is_validated():
    emitter = EventEmitter()
    received: list[DomainEvent] = []
    emitter.register(EventName.MESSAGE_RECEIVED, received.append)
    payload = {
        "tenant_id": uuid.uuid4(),
        "message_id": "provider-message-1",
        "provider": "whatsapp",
        "occurred_at": datetime.now(UTC),
    }

    emitter.publish(EventName.MESSAGE_RECEIVED, payload)

    assert received[0].name is EventName.MESSAGE_RECEIVED
    assert received[0].payload == MessageReceivedPayload.model_validate(payload)


@pytest.mark.parametrize("event_name", ["unknown", "lead.created.extra"])
def test_unknown_event_names_are_rejected(event_name):
    emitter = EventEmitter()

    with pytest.raises(UnknownEventError):
        emitter.publish(event_name, _lead_payload())

    with pytest.raises(UnknownEventError):
        emitter.register(event_name, lambda event: None)


@pytest.mark.parametrize(
    "payload",
    [
        {"tenant_id": uuid.uuid4()},
        {**_lead_payload(), "unexpected": "field"},
        {**_lead_payload(), "occurred_at": datetime.now()},
    ],
)
def test_invalid_payloads_are_rejected(payload):
    emitter = EventEmitter()

    with pytest.raises(EventPayloadError):
        emitter.publish(EventName.LEAD_CREATED, payload)


def test_handler_failure_is_explicit_and_chained():
    emitter = EventEmitter()

    def fail(_event):
        raise RuntimeError("handler broke")

    emitter.register(EventName.LEAD_CREATED, fail)

    with pytest.raises(EventHandlerError) as error:
        emitter.publish(EventName.LEAD_CREATED, _lead_payload())

    assert isinstance(error.value.__cause__, RuntimeError)
