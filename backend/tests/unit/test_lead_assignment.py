from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest

from app.modules.auth.errors import AuthError
from app.modules.leads import service
from app.modules.leads.schemas import LeadAssignRequest
from app.modules.audit.models import AuditLog
from app.modules.leads.models import Interaction


def make_context(role="admin", team_id=None):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
    )


def make_lead(context):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=context.tenant_id,
        assigned_user_id=None,
        team_id=None,
        status="new",
    )


def make_body():
    return LeadAssignRequest(
        assigned_user_id=uuid.uuid4(),
        team_id=uuid.uuid4(),
    )


def test_assign_lead_success_creates_audit_and_timeline():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context)
    body = make_body()
    membership = SimpleNamespace(
        user_id=body.assigned_user_id,
        team_id=body.team_id,
    )
    session.scalar.side_effect = [lead, membership]

    result = service.assign_lead(session, context, lead.id, body)

    assert result["id"] == str(lead.id)
    assert result["assigned_user_id"] == str(body.assigned_user_id)
    assert result["team_id"] == str(body.team_id)
    assert lead.assigned_user_id == body.assigned_user_id
    assert lead.team_id == body.team_id
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(lead)

    added = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(item, Interaction) for item in added)
    assert any(
        isinstance(item, AuditLog) and item.action == "lead.assigned"
        for item in added
    )


def test_assign_lead_rejects_missing_lead():
    session = MagicMock()
    context = make_context()
    body = make_body()
    session.scalar.return_value = None

    with pytest.raises(AuthError) as exc:
        service.assign_lead(session, context, uuid.uuid4(), body)

    assert exc.value.status_code == 404
    session.commit.assert_not_called()


def test_manager_cannot_assign_lead_outside_own_team():
    context = make_context(role="manager", team_id=uuid.uuid4())
    session = MagicMock()
    lead = make_lead(context)
    lead.team_id = uuid.uuid4()
    body = make_body()
    session.scalar.return_value = lead

    with pytest.raises(AuthError) as exc:
        service.assign_lead(session, context, lead.id, body)

    assert exc.value.status_code == 403
    session.commit.assert_not_called()
