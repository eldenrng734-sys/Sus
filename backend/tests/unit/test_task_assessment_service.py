import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.modules.tasks.service import create_assessment_follow_up


def make_assessment(**overrides):
    values = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "lead_id": uuid.uuid4(),
        "recommended_action": "call",
        "follow_up_days": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_creates_tenant_scoped_idempotent_task_with_recommended_due_date():
    assessment = make_assessment()
    lead = SimpleNamespace(
        id=assessment.lead_id,
        assigned_user_id=uuid.uuid4(),
        team_id=uuid.uuid4(),
    )
    existing_or_created_task = SimpleNamespace(id=uuid.uuid4())
    session = MagicMock()
    session.scalar.return_value = existing_or_created_task

    task = create_assessment_follow_up(session, assessment, lead)

    assert task is existing_or_created_task
    session.execute.assert_called_once()
    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT" in str(compiled)
    assert "DO NOTHING" in str(compiled)
    assert compiled.params["tenant_id"] == assessment.tenant_id
    assert compiled.params["lead_id"] == assessment.lead_id
    assert compiled.params["assigned_user_id"] == lead.assigned_user_id
    assert compiled.params["team_id"] == lead.team_id
    assert compiled.params["type"] == "call"
    assert compiled.params["created_by"] == "automation"
    assert compiled.params["idempotency_key"] == f"assessment:{assessment.id}:follow-up"
    due_at = compiled.params["due_at"]
    assert due_at >= datetime.now(UTC)
    assert (due_at - datetime.now(UTC)).days == 2


def test_action_maps_to_supported_task_type_and_defaults_when_days_missing():
    assessment = make_assessment(
        recommended_action="schedule_demo",
        follow_up_days=None,
    )
    lead = SimpleNamespace(
        id=assessment.lead_id,
        assigned_user_id=None,
        team_id=None,
    )
    session = MagicMock()

    create_assessment_follow_up(session, assessment, lead)

    compiled = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert compiled.params["type"] == "meeting"
    assert compiled.params["title"] == "Schedule a demo"
    assert (compiled.params["due_at"] - datetime.now(UTC)).total_seconds() < 60


def test_repeated_assessment_uses_same_deduplication_key():
    assessment = make_assessment()
    lead = SimpleNamespace(
        id=assessment.lead_id,
        assigned_user_id=None,
        team_id=None,
    )
    existing_task = SimpleNamespace(id=uuid.uuid4())
    session = MagicMock()
    session.scalar.return_value = existing_task

    first = create_assessment_follow_up(session, assessment, lead)
    second = create_assessment_follow_up(session, assessment, lead)

    assert first is second is existing_task
    assert session.execute.call_count == 2
    first_insert = session.execute.call_args_list[0].args[0]
    second_insert = session.execute.call_args_list[1].args[0]
    assert first_insert.compile(dialect=postgresql.dialect()).params["idempotency_key"] == (
        second_insert.compile(dialect=postgresql.dialect()).params["idempotency_key"]
    )


def test_no_task_is_created_when_recommended_action_is_not_actionable():
    assessment = make_assessment(recommended_action="none")
    session = MagicMock()

    result = create_assessment_follow_up(session, assessment, SimpleNamespace())

    assert result is None
    session.execute.assert_not_called()
    session.scalar.assert_not_called()
