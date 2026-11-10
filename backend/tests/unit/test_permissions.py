import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Lead
from app.modules.tasks.models import Task


def make_context(role, team_id=None):
    return TenantContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
        session_id=uuid.uuid4(),
    )


def compile_query(statement):
    return statement.compile(
        dialect=postgresql.dialect()
    )


def test_rep_scope_is_own_assigned_leads():
    context = make_context("rep")
    compiled = compile_query(apply_data_scope(select(Lead), Lead, context))

    assert context.tenant_id in compiled.params.values()
    assert context.user_id in compiled.params.values()
    assert "assigned_user_id" in str(compiled)


def test_manager_scope_is_team_leads():
    team_id = uuid.uuid4()
    context = make_context("manager", team_id)
    compiled = compile_query(apply_data_scope(select(Lead), Lead, context))

    assert team_id in compiled.params.values()
    assert context.tenant_id in compiled.params.values()
    assert "team_id" in str(compiled)


def test_admin_scope_is_tenant_leads():
    context = make_context("admin")
    compiled = compile_query(apply_data_scope(select(Lead), Lead, context))

    assert context.tenant_id in compiled.params.values()
    assert "tenant_id" in str(compiled)


def test_manager_without_team_gets_no_records():
    context = make_context("manager")
    compiled = compile_query(apply_data_scope(select(Lead), Lead, context))

    assert "false" in str(compiled).lower()


def test_unknown_role_is_forbidden():
    context = make_context("unknown")

    with pytest.raises(AuthError):
        apply_data_scope(select(Lead), Lead, context)


def test_rep_task_scope_uses_assigned_user():
    context = make_context("rep")
    compiled = compile_query(apply_data_scope(select(Task), Task, context))

    assert context.user_id in compiled.params.values()
    assert "assigned_user_id" in str(compiled)


def test_manager_task_scope_uses_team():
    team_id = uuid.uuid4()
    context = make_context("manager", team_id)
    compiled = compile_query(apply_data_scope(select(Task), Task, context))

    assert team_id in compiled.params.values()
    assert "team_id" in str(compiled)
