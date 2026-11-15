import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.audit.models import AuditLog
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Interaction
from app.modules.leads.optout import (
    apply_opt_out,
    can_message,
    is_opt_out_message,
    normalize,
)


@pytest.mark.parametrize(
    "message",
    [
        "STOP",
        "Stop.",
        "  stop  ",
        "STOP!!!",
        "unsubscribe",
        "বন্ধ",
        "বন্ধ করুন",
        "Opt-Out",
    ],
)
def test_opt_out_command_variants(message):
    assert is_opt_out_message(message)


@pytest.mark.parametrize(
    "message",
    [
        "please don't stop the demo",
        "I want to stop by tomorrow",
        "Hello",
        "stop now",
        "",
    ],
)
def test_non_opt_out_messages(message):
    assert not is_opt_out_message(message)


def test_normalize_preserves_bangla_vowel_marks():
    assert normalize("  বন্ধ করুন।  ") == "বন্ধ করুন"


@pytest.mark.parametrize(
    ("opted_out", "consent", "expected"),
    [
        (True, True, (False, "opt_out")),
        (True, False, (False, "opt_out")),
        (False, False, (False, "no_consent")),
        (False, True, (True, None)),
    ],
)
def test_can_message(opted_out, consent, expected):
    lead = SimpleNamespace(opted_out=opted_out, consent=consent)

    assert can_message(lead) == expected


def test_apply_opt_out_records_state_cancels_followups_and_audits():
    lead = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        opted_out=False,
        opted_out_at=None,
        opted_out_source=None,
        version=3,
    )
    actor_user_id = uuid.uuid4()
    session = MagicMock()
    session.scalar.return_value = lead
    session.execute.return_value.scalar.return_value = None  # no tasks table in this context

    assert apply_opt_out(session, lead.id, "messenger", actor_user_id) is True

    assert lead.opted_out is True
    assert isinstance(lead.opted_out_at, datetime)
    assert lead.opted_out_at.tzinfo == UTC
    assert lead.opted_out_source == "messenger"
    assert lead.version == 4
    session.execute.assert_called_once()
    session.commit.assert_called_once()

    added = [call.args[0] for call in session.add.call_args_list]
    interaction = next(item for item in added if isinstance(item, Interaction))
    audit = next(item for item in added if isinstance(item, AuditLog))
    assert interaction.type == "opt_out"
    assert interaction.source == "messenger"
    assert interaction.created_by_user_id == actor_user_id
    assert audit.action == "lead.opted_out"
    assert audit.actor_user_id == actor_user_id
    assert audit.details == {"source": "messenger"}


def test_apply_opt_out_is_idempotent_for_an_already_opted_out_lead():
    lead = SimpleNamespace(id=uuid.uuid4(), opted_out=True)
    session = MagicMock()
    session.scalar.return_value = lead

    assert apply_opt_out(session, lead.id, "whatsapp") is False

    session.execute.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_apply_opt_out_returns_not_found_for_missing_lead():
    session = MagicMock()
    session.scalar.return_value = None
    lead_id = uuid.uuid4()

    with pytest.raises(AuthError) as exc:
        apply_opt_out(session, lead_id, "manual")

    assert exc.value.status_code == 404
    session.commit.assert_not_called()


def test_apply_opt_out_rolls_back_when_a_write_fails():
    lead = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        opted_out=False,
        version=1,
    )
    session = MagicMock()
    session.scalar.return_value = lead
    session.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        apply_opt_out(session, lead.id, "api")

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
