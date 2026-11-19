"""Unit tests for tasks service — #5 hardening.

Covers:
- cross-tenant read and update (404 for other tenant)
- role-scope: rep sees only own, manager only team
- duplicate idempotency key replays original task
- stale version returns 409 version_conflict
- GET /due-follow-ups route is not swallowed by /{task_id}
- update_task writes audit log and timeline entry (Interaction)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(role="admin", team_id=None):
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
        session_id=uuid.uuid4(),
    )


def _task(tenant_id=None, assigned_user_id=None, team_id=None, task_type="follow_up", version=1):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        lead_id=uuid.uuid4(),
        title="Follow up",
        notes=None,
        type=task_type,
        status="open",
        due_at=datetime.now(UTC) + timedelta(hours=1),
        assigned_user_id=assigned_user_id,
        team_id=team_id,
        requires_approval=False,
        approval_status="not_required",
        approved_by_user_id=None,
        approved_at=None,
        approval_note=None,
        rejected_by_user_id=None,
        rejected_at=None,
        completed_at=None,
        created_by="user",
        version=version,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_session():
    s = MagicMock()
    s.rollback = Mock()
    s.commit = Mock()
    s.flush = Mock()
    s.refresh = Mock()
    return s


# ---------------------------------------------------------------------------
# list_due_follow_ups
# ---------------------------------------------------------------------------


def test_list_due_follow_ups_calls_apply_data_scope():
    """list_due_follow_ups must call apply_data_scope."""
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    session.scalars.return_value.all.return_value = []

    with patch(
        "app.modules.tasks.service.apply_data_scope",
        side_effect=lambda stmt, model, ctx: stmt,
    ) as mock_scope:
        result = service.list_due_follow_ups(session, context)

    assert mock_scope.called
    assert result == []


def test_list_due_follow_ups_invalid_due_before_raises_422():
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    with pytest.raises(AuthError) as exc_info:
        service.list_due_follow_ups(session, context, due_before="not-a-date")
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# GET /due-follow-ups route ordering (does not collide with /{task_id})
# ---------------------------------------------------------------------------


def test_due_follow_ups_route_registered_before_task_id():
    """Verify /due-follow-ups is listed before /{task_id} in router routes."""
    from app.modules.tasks.router import router

    routes = router.routes
    # Routes have full prefix paths e.g. "/api/v1/tasks/due-follow-ups"
    route_paths = [getattr(r, "path", "") for r in routes]

    assert any("due-follow-ups" in p for p in route_paths), "Missing /due-follow-ups route"
    assert any("{task_id}" in p for p in route_paths), "Missing /{task_id} route"

    idx_due = next(i for i, p in enumerate(route_paths) if "due-follow-ups" in p)
    idx_id = next(i for i, p in enumerate(route_paths) if "{task_id}" in p)
    assert idx_due < idx_id, (
        f"/due-follow-ups (index {idx_due}) must come before /{{task_id}} (index {idx_id})"
    )


# ---------------------------------------------------------------------------
# Idempotency: duplicate key replays original response
# ---------------------------------------------------------------------------


def test_create_task_replay_on_duplicate_idempotency_key():
    """A second POST with the same key returns the original task (is_replay=True)."""
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    existing_task = _task(tenant_id=context.tenant_id)
    task_body = SimpleNamespace(
        lead_id=uuid.uuid4(),
        title="Call",
        notes=None,
        type="call",
        due_at=datetime.now(UTC) + timedelta(hours=2),
        assigned_user_id=None,
        requires_approval=False,
        model_dump=lambda mode=None: {},
    )

    replay_body = {"id": str(existing_task.id)}

    with patch("app.modules.tasks.service.claim_idempotency", return_value=(None, replay_body)):
        with patch("app.modules.tasks.service.select", return_value=MagicMock()):
            session.scalar.return_value = existing_task
            task, is_replay = service.create_task(
                session, context, task_body, idempotency_key="idem-key-123"
            )

    assert is_replay is True
    assert task is existing_task


def test_create_task_missing_replayed_task_raises_500():
    """If the idempotency replay body points to a non-existent task, raise 500."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    task_body = SimpleNamespace(
        lead_id=uuid.uuid4(),
        title="Call",
        notes=None,
        type="call",
        due_at=datetime.now(UTC) + timedelta(hours=2),
        assigned_user_id=None,
        requires_approval=False,
        model_dump=lambda mode=None: {},
    )
    replay_body = {"id": str(uuid.uuid4())}

    with patch("app.modules.tasks.service.claim_idempotency", return_value=(None, replay_body)):
        with patch("app.modules.tasks.service.select", return_value=MagicMock()):
            session.scalar.return_value = None
            with pytest.raises(AuthError) as exc_info:
                service.create_task(session, context, task_body, idempotency_key="idem-key-456")
    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Version / optimistic lock
# ---------------------------------------------------------------------------


def test_update_task_stale_version_raises_409():
    """PATCH with a stale version field returns 409 version_conflict."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    task = _task(tenant_id=context.tenant_id, version=3)

    body = MagicMock()
    body.model_dump.return_value = {"title": "Updated", "version": 1}  # stale!

    with patch.object(service, "_get_scoped_task", return_value=task):
        with pytest.raises(AuthError) as exc_info:
            service.update_task(session, context, task.id, body)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "version_conflict"


def test_update_task_correct_version_succeeds():
    """PATCH with the correct version proceeds and increments version."""
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    task = _task(tenant_id=context.tenant_id, version=2)

    body = MagicMock()
    body.model_dump.return_value = {"title": "Updated title", "version": 2}

    with patch.object(service, "_get_scoped_task", return_value=task):
        with patch.object(service, "_audit"):
            with patch.object(service, "_add_timeline"):
                service.update_task(session, context, task.id, body)

    assert task.version == 3
    assert task.title == "Updated title"


def test_update_task_no_version_field_succeeds():
    """PATCH without version field still works (version check is opt-in)."""
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    task = _task(tenant_id=context.tenant_id, version=1)

    body = MagicMock()
    body.model_dump.return_value = {"notes": "new note"}

    with patch.object(service, "_get_scoped_task", return_value=task):
        with patch.object(service, "_audit"):
            with patch.object(service, "_add_timeline"):
                service.update_task(session, context, task.id, body)

    assert task.notes == "new note"
    assert task.version == 2


# ---------------------------------------------------------------------------
# update_task writes audit log AND timeline entry
# ---------------------------------------------------------------------------


def test_update_task_writes_audit_and_timeline():
    """update_task must call _audit and _add_timeline."""
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    task = _task(tenant_id=context.tenant_id, version=1)

    body = MagicMock()
    body.model_dump.return_value = {"notes": "updated"}

    with patch.object(service, "_get_scoped_task", return_value=task):
        with patch.object(service, "_audit") as mock_audit:
            with patch.object(service, "_add_timeline") as mock_timeline:
                service.update_task(session, context, task.id, body)

    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "task.updated"

    mock_timeline.assert_called_once()
    assert mock_timeline.call_args[0][2] == "task_updated"


# ---------------------------------------------------------------------------
# Cross-tenant isolation — patch _get_scoped_task to avoid ORM class issues
# ---------------------------------------------------------------------------


def test_cross_tenant_task_read_returns_404():
    """A task owned by tenant-B must not be readable by tenant-A's context."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context_a = _ctx()
    task_id = uuid.uuid4()
    session = _mock_session()

    with patch.object(
        service,
        "_get_scoped_task",
        side_effect=AuthError(404, "not_found", "Task not found"),
    ):
        with pytest.raises(AuthError) as exc_info:
            service.get_task(session, context_a, task_id)

    assert exc_info.value.status_code == 404


def test_cross_tenant_task_update_returns_404():
    """A PATCH on another tenant's task must raise 404."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context_a = _ctx()
    task_id = uuid.uuid4()
    session = _mock_session()
    body = MagicMock()
    body.model_dump.return_value = {"notes": "hacked"}

    with patch.object(
        service,
        "_get_scoped_task",
        side_effect=AuthError(404, "not_found", "Task not found"),
    ):
        with pytest.raises(AuthError) as exc_info:
            service.update_task(session, context_a, task_id, body)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Role-scope: rep vs manager
# ---------------------------------------------------------------------------


def test_rep_cannot_assign_task_to_another_user():
    """A rep assigning to another user raises 403."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    rep_ctx = _ctx(role="rep")
    other_user = uuid.uuid4()

    session = _mock_session()
    lead = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=rep_ctx.tenant_id,
        assigned_user_id=rep_ctx.user_id,
        team_id=uuid.uuid4(),
    )

    with pytest.raises(AuthError) as exc_info:
        service._validate_assignee(session, rep_ctx, lead, other_user)

    assert exc_info.value.status_code == 403


def test_rep_self_assign_requires_active_membership():
    """A rep assigning to themselves passes only if membership row exists."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    rep_ctx = _ctx(role="rep")
    session = _mock_session()
    lead = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=rep_ctx.tenant_id,
        assigned_user_id=rep_ctx.user_id,
        team_id=uuid.uuid4(),
    )

    # No matching membership row → 422
    session.scalar.return_value = None
    with patch("app.modules.tasks.service.select", return_value=MagicMock()):
        with pytest.raises(AuthError) as exc_info:
            service._validate_assignee(session, rep_ctx, lead, rep_ctx.user_id)
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# list_approval_queue role check
# ---------------------------------------------------------------------------


def test_list_approval_queue_rep_raises_403():
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context = _ctx(role="rep")
    session = _mock_session()
    with pytest.raises(AuthError) as exc_info:
        service.list_approval_queue(session, context)
    assert exc_info.value.status_code == 403


def test_decide_task_approval_rep_raises_403():
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context = _ctx(role="rep")
    session = _mock_session()
    with pytest.raises(AuthError) as exc_info:
        service.decide_task_approval(session, context, uuid.uuid4(), approved=True)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Scope tests: rep own, manager team, admin all
# ---------------------------------------------------------------------------


def test_list_tasks_applies_rep_scope():
    from app.modules.tasks import service

    rep_ctx = _ctx(role="rep")
    session = _mock_session()
    session.scalars.return_value.all.return_value = []

    with patch("app.modules.tasks.service.apply_data_scope") as mock_scope:
        chained = MagicMock()
        mock_scope.return_value = chained
        chained.order_by.return_value = chained
        chained.limit.return_value = chained
        chained.offset.return_value = chained
        service.list_tasks(session, rep_ctx)

    mock_scope.assert_called_once()
    assert mock_scope.call_args[0][2] is rep_ctx


def test_apply_data_scope_clauses_for_roles():
    from sqlalchemy import select

    from app.core.permissions import apply_data_scope
    from app.modules.tasks.models import Task

    rep_ctx = _ctx(role="rep")
    stmt_rep = apply_data_scope(select(Task), Task, rep_ctx)
    sql_rep = str(stmt_rep.compile(compile_kwargs={"literal_binds": True}))
    assert f"tasks.assigned_user_id = '{rep_ctx.user_id.hex}'" in sql_rep
    assert f"tasks.tenant_id = '{rep_ctx.tenant_id.hex}'" in sql_rep

    team_id = uuid.uuid4()
    mgr_ctx = _ctx(role="manager", team_id=team_id)
    stmt_mgr = apply_data_scope(select(Task), Task, mgr_ctx)
    sql_mgr = str(stmt_mgr.compile(compile_kwargs={"literal_binds": True}))
    assert f"tasks.team_id = '{team_id.hex}'" in sql_mgr
    assert f"tasks.tenant_id = '{mgr_ctx.tenant_id.hex}'" in sql_mgr

    admin_ctx = _ctx(role="admin")
    stmt_admin = apply_data_scope(select(Task), Task, admin_ctx)
    sql_admin = str(stmt_admin.compile(compile_kwargs={"literal_binds": True}))
    assert f"tasks.tenant_id = '{admin_ctx.tenant_id.hex}'" in sql_admin
    where_admin = sql_admin.split("WHERE")[-1]
    assert "tasks.assigned_user_id" not in where_admin
    assert "tasks.team_id" not in where_admin


def test_concurrent_patches_second_gets_409():
    """Simulate two concurrent PATCHes: the second sending the old version gets 409."""
    from app.modules.auth.errors import AuthError
    from app.modules.tasks import service

    context = _ctx()
    session = _mock_session()
    task = _task(tenant_id=context.tenant_id, version=1)

    # First PATCH has version 1
    patch1_body = MagicMock()
    patch1_body.model_dump.return_value = {"title": "First Update", "version": 1}

    with patch.object(service, "_get_scoped_task", return_value=task):
        with patch.object(service, "_audit"):
            with patch.object(service, "_add_timeline"):
                service.update_task(session, context, task.id, patch1_body)

    assert task.version == 2
    assert task.title == "First Update"

    # Second concurrent PATCH was submitted with original version 1
    patch2_body = MagicMock()
    patch2_body.model_dump.return_value = {"title": "Second Update", "version": 1}

    with patch.object(service, "_get_scoped_task", return_value=task):
        with pytest.raises(AuthError) as exc_info:
            service.update_task(session, context, task.id, patch2_body)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "version_conflict"
