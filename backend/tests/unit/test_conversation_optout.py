import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.messaging import service


def make_context(role: str, team_id: uuid.UUID | None = None) -> TenantContext:
    return TenantContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
        session_id=uuid.uuid4(),
    )


def test_rep_can_message_own_lead():
    context = make_context("rep")
    lead = SimpleNamespace(
        assigned_user_id=context.user_id,
        team_id=uuid.uuid4(),
        opted_out=False,
    )

    service.ensure_lead_authorized(context, lead)


def test_rep_cannot_message_another_reps_lead():
    context = make_context("rep")
    lead = SimpleNamespace(
        assigned_user_id=uuid.uuid4(),
        team_id=context.team_id,
        opted_out=False,
    )

    with pytest.raises(AuthError) as exc:
        service.ensure_lead_authorized(context, lead)

    assert exc.value.status_code == 403
    assert exc.value.code == "forbidden"


def test_manager_can_message_team_lead_only():
    team_id = uuid.uuid4()
    context = make_context("manager", team_id)
    own_team_lead = SimpleNamespace(assigned_user_id=uuid.uuid4(), team_id=team_id)
    other_team_lead = SimpleNamespace(assigned_user_id=uuid.uuid4(), team_id=uuid.uuid4())

    service.ensure_lead_authorized(context, own_team_lead)
    with pytest.raises(AuthError):
        service.ensure_lead_authorized(context, other_team_lead)


def test_admin_can_message_any_tenant_lead():
    context = make_context("admin")
    lead = SimpleNamespace(assigned_user_id=uuid.uuid4(), team_id=uuid.uuid4())

    service.ensure_lead_authorized(context, lead)


def test_opted_out_lead_is_rejected():
    lead = SimpleNamespace(opted_out=True, consent=True)

    with pytest.raises(AuthError) as exc:
        service.ensure_not_opted_out(lead)

    assert exc.value.status_code == 403
    assert exc.value.code == "opted_out"


def test_window_closed_after_24_hours():
    conversation = SimpleNamespace(
        last_inbound_at=datetime.now(UTC) - timedelta(hours=24, seconds=1)
    )

    with pytest.raises(AuthError) as exc:
        service.ensure_window_open(conversation)

    assert exc.value.status_code == 409
    assert exc.value.code == "window_closed"


def test_window_open_for_recent_inbound_and_boundary():
    now = datetime.now(UTC)
    service.ensure_window_open(SimpleNamespace(last_inbound_at=now), now=now)
    service.ensure_window_open(
        SimpleNamespace(last_inbound_at=now - timedelta(hours=23, minutes=59)),
        now=now,
    )


def test_template_payload_uses_whatsapp_shape():
    payload = service.build_template_payload("demo_follow_up", "en_US", ["Ayesha", "3 PM"])

    assert payload["type"] == "template"
    assert payload["template"]["name"] == "demo_follow_up"
    assert payload["template"]["language"] == {"code": "en_US"}
    assert payload["template"]["components"] == [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Ayesha"},
                {"type": "text", "text": "3 PM"},
            ],
        }
    ]
