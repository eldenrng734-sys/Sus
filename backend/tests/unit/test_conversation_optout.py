import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.auth.errors import AuthError
from app.modules.conversations import service


@pytest.mark.parametrize(
    ("lead", "expected_code"),
    [
        (SimpleNamespace(opted_out=True, consent=True), "opt_out"),
        (SimpleNamespace(opted_out=False, consent=False), "no_consent"),
    ],
)
def test_send_message_rejects_ineligible_lead(monkeypatch, lead, expected_code):
    conversation = SimpleNamespace(channel="messenger", lead_id=uuid.uuid4())
    monkeypatch.setattr(service, "_get_conversation", lambda *args: conversation)
    monkeypatch.setattr(service, "_get_lead", lambda *args: lead)
    session = MagicMock()

    with pytest.raises(AuthError) as exc:
        service.send_message(
            session,
            SimpleNamespace(),
            SimpleNamespace(conversation_id=uuid.uuid4()),
        )

    assert exc.value.status_code == 403
    assert exc.value.code == expected_code
    session.add.assert_not_called()
    session.commit.assert_not_called()
