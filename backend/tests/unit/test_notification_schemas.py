import uuid

import pytest
from pydantic import ValidationError

from app.modules.notifications.schemas import NotificationCreateRequest


def payload(**updates):
    value = {
        "user_id": str(uuid.uuid4()),
        "type": "new_lead",
        "title": "New lead",
        "body": "A new lead is assigned to you.",
        "entity_type": "lead",
        "entity_id": str(uuid.uuid4()),
    }
    value.update(updates)
    return value


def test_notification_request_accepts_only_the_documented_fields():
    request = NotificationCreateRequest.model_validate(payload())

    assert set(request.model_dump()) == {
        "user_id",
        "type",
        "title",
        "body",
        "entity_type",
        "entity_id",
    }


@pytest.mark.parametrize(
    "updates",
    [
        {"unknown": "value"},
        {"type": "message_received"},
        {"entity_type": "conversation"},
        {"user_id": "not-a-uuid"},
        {"entity_id": "not-a-uuid"},
        {"title": "   "},
        {"body": "\n\t"},
        {"title": "t" * 201},
        {"body": "b" * 2001},
    ],
)
def test_notification_request_rejects_invalid_fields(updates):
    with pytest.raises(ValidationError):
        NotificationCreateRequest.model_validate(payload(**updates))


def test_notification_request_trims_surrounding_whitespace():
    request = NotificationCreateRequest.model_validate(
        payload(title="  New lead  ", body="  A new lead is assigned.  ")
    )

    assert request.title == "New lead"
    assert request.body == "A new lead is assigned."
