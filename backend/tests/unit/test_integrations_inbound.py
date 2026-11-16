import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.conversations.models import Conversation, Message
from app.modules.integrations import inbound
from app.modules.integrations.inbound import InboundMessage


def test_stored_inbound_message_enqueues_message_received(monkeypatch):
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    lead = SimpleNamespace(id=lead_id, assigned_user_id=None)
    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel="whatsapp",
        status="open",
    )
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = conversation
    session.add.side_effect = lambda value: (
        setattr(value, "id", message_id) if isinstance(value, Message) else None
    )
    monkeypatch.setattr(
        inbound,
        "capture_lead",
        lambda *_args, **_kwargs: SimpleNamespace(lead=lead),
    )
    enqueue = MagicMock()
    monkeypatch.setattr(inbound, "emit_message_received", enqueue)

    result = inbound.store_inbound_message(
        session,
        tenant_id=tenant_id,
        inbound=InboundMessage(
            provider="whatsapp",
            channel="whatsapp",
            source="whatsapp",
            account_id="phone-number-1",
            external_contact_id="+15555550123",
            external_conversation_id="+15555550123",
            external_lead_id="+15555550123",
            contact_name="Customer",
            message_id="wamid.1",
            body_text="Please send information",
        ),
    )

    assert result.message is not None
    enqueue.assert_called_once_with(
        session,
        tenant_id=tenant_id,
        message_id=message_id,
        conversation_id=conversation_id,
    )
