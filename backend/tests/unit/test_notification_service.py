import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.service_auth import InternalServiceContext
from app.modules.auth.errors import AuthError
from app.modules.notifications import service
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationCreateRequest


def make_context(tenant_id=None, request_hash="a" * 64):
    return InternalServiceContext(
        service_id="n8n",
        tenant_id=tenant_id or uuid.uuid4(),
        idempotency_key="notification-key-123",
        body_sha256=request_hash,
    )


def make_request(**updates):
    value = {
        "user_id": uuid.uuid4(),
        "type": "new_lead",
        "title": "New lead",
        "body": "A new lead is assigned to you.",
        "entity_type": "lead",
        "entity_id": uuid.uuid4(),
    }
    value.update(updates)
    return NotificationCreateRequest.model_validate(value)


def configure_success(session, context, request):
    lead = SimpleNamespace(
        tenant_id=context.tenant_id,
        id=request.entity_id,
        assigned_user_id=request.user_id,
    )
    membership = SimpleNamespace(role="rep", is_active=True)
    user = SimpleNamespace(is_active=True)
    session.scalar.side_effect = [
        SimpleNamespace(status="active"),
        uuid.uuid4(),
        lead,
    ]
    recipient_result = MagicMock()
    recipient_result.first.return_value = (membership, user)
    session.execute.side_effect = [None, recipient_result, None]


def test_create_notification_validates_recipient_and_owned_lead_atomically():
    session = MagicMock()
    context = make_context()
    request = make_request()
    configure_success(session, context, request)

    service.create_notification(session, context, request)

    notification = next(
        item
        for item in (call.args[0] for call in session.add.call_args_list)
        if isinstance(item, Notification)
    )
    assert notification.tenant_id == context.tenant_id
    assert notification.user_id == request.user_id
    assert notification.entity_id == request.entity_id
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_inactive_or_nonrep_recipient_is_rejected_without_persisting():
    session = MagicMock()
    context = make_context()
    request = make_request()
    session.scalar.side_effect = [SimpleNamespace(status="active"), uuid.uuid4()]
    recipient_result = MagicMock()
    recipient_result.first.return_value = None
    session.execute.side_effect = [None, recipient_result]

    with pytest.raises(AuthError) as error:
        service.create_notification(session, context, request)

    assert error.value.status_code == 403
    assert not any(isinstance(call.args[0], Notification) for call in session.add.call_args_list)
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    "membership,user",
    [
        (SimpleNamespace(role="manager", is_active=True), SimpleNamespace(is_active=True)),
        (SimpleNamespace(role="rep", is_active=False), SimpleNamespace(is_active=True)),
        (SimpleNamespace(role="rep", is_active=True), SimpleNamespace(is_active=False)),
    ],
)
def test_recipient_role_and_active_state_are_checked(membership, user):
    session = MagicMock()
    context = make_context()
    request = make_request()
    session.scalar.side_effect = [SimpleNamespace(status="active"), uuid.uuid4()]
    recipient_result = MagicMock()
    recipient_result.first.return_value = (membership, user)
    session.execute.side_effect = [None, recipient_result]

    with pytest.raises(AuthError) as error:
        service.create_notification(session, context, request)

    assert error.value.status_code == 403
    session.add.assert_not_called()
    session.rollback.assert_called_once()


@pytest.mark.parametrize("tenant", [None, SimpleNamespace(status="suspended")])
def test_missing_or_inactive_tenant_is_rejected(tenant):
    session = MagicMock()
    context = make_context()
    session.scalar.return_value = tenant

    with pytest.raises(AuthError):
        service.create_notification(session, context, make_request())

    session.execute.assert_called_once()
    session.rollback.assert_called_once()
    session.add.assert_not_called()


def test_recipient_must_own_the_lead():
    session = MagicMock()
    context = make_context()
    request = make_request()
    other_user_id = uuid.uuid4()
    lead = SimpleNamespace(
        tenant_id=context.tenant_id,
        id=request.entity_id,
        assigned_user_id=other_user_id,
    )
    session.scalar.side_effect = [
        SimpleNamespace(status="active"),
        uuid.uuid4(),
        lead,
    ]
    recipient_result = MagicMock()
    recipient_result.first.return_value = (
        SimpleNamespace(role="rep", is_active=True),
        SimpleNamespace(is_active=True),
    )
    session.execute.side_effect = [None, recipient_result]

    with pytest.raises(AuthError) as error:
        service.create_notification(session, context, request)

    assert error.value.status_code == 403
    assert not any(isinstance(call.args[0], Notification) for call in session.add.call_args_list)
    session.rollback.assert_called_once()


def test_cross_tenant_or_missing_lead_is_not_found():
    session = MagicMock()
    context = make_context()
    request = make_request()
    session.scalar.side_effect = [
        SimpleNamespace(status="active"),
        uuid.uuid4(),
        None,
    ]
    recipient_result = MagicMock()
    recipient_result.first.return_value = (
        SimpleNamespace(role="rep", is_active=True),
        SimpleNamespace(is_active=True),
    )
    session.execute.side_effect = [None, recipient_result]

    with pytest.raises(AuthError) as error:
        service.create_notification(session, context, request)

    assert error.value.status_code == 404
    session.rollback.assert_called_once()


def test_same_idempotency_key_replays_without_duplicate_insert():
    session = MagicMock()
    context = make_context()
    request = make_request()
    existing = SimpleNamespace(
        request_hash=context.body_sha256,
        response_status=202,
        response_body={},
    )
    session.scalar.side_effect = [SimpleNamespace(status="active"), None, existing]
    session.execute.return_value = None

    service.create_notification(session, context, request)

    session.commit.assert_called_once()
    session.add.assert_not_called()


def test_same_idempotency_key_with_different_body_conflicts():
    session = MagicMock()
    context = make_context()
    request = make_request()
    existing = SimpleNamespace(
        request_hash="b" * 64,
        response_status=202,
        response_body={},
    )
    session.scalar.side_effect = [SimpleNamespace(status="active"), None, existing]
    session.execute.return_value = None

    with pytest.raises(AuthError) as error:
        service.create_notification(session, context, request)

    assert error.value.status_code == 409
    session.add.assert_not_called()
    session.rollback.assert_called_once()
