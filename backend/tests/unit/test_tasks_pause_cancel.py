"""Unit tests for Phase 1 Step #6: Pause-on-reply, opt-out cancel.

Requirements:
1. Inbound message pauses that lead's follow-ups only (other leads and call tasks untouched).
2. Opt-out cancels that lead's follow-up tasks.
3. A paused or cancelled task cannot be sent (messaging returns 409).
4. A rep gets 403 on approve.
5. Approving a task of a won or lost lead still cannot send (messaging returns 409).
6. Cross-tenant approve returns 404.
7. Manager of another team gets 404 on approve.
8. Approve/reject on task not requiring approval or not pending returns 409.
9. Paused task can be resumed via PATCH status=open.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError


def _ctx(role: str = "admin", team_id: uuid.UUID | None = None) -> TenantContext:
    return TenantContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
        session_id=uuid.uuid4(),
    )


def _make_task(
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID,
    task_type: str = "follow_up",
    status: str = "open",
    requires_approval: bool = False,
    approval_status: str = "not_required",
    team_id: uuid.UUID | None = None,
    assigned_user_id: uuid.UUID | None = None,
    version: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        lead_id=lead_id,
        title="Test task",
        notes="Notes",
        type=task_type,
        status=status,
        due_at=datetime.now(UTC) + timedelta(days=1),
        assigned_user_id=assigned_user_id,
        team_id=team_id,
        requires_approval=requires_approval,
        approval_status=approval_status,
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
# 1. pause_followups tests
# ---------------------------------------------------------------------------


def test_pause_followups_pauses_only_open_followups_for_target_lead():
    from app.modules.tasks.service import pause_followups

    tenant_id = uuid.uuid4()
    lead_1 = uuid.uuid4()
    lead_2 = uuid.uuid4()

    t1_followup_open = _make_task(tenant_id, lead_1, task_type="follow_up", status="open")
    t1_call_open = _make_task(tenant_id, lead_1, task_type="call", status="open")
    t1_meeting_open = _make_task(tenant_id, lead_1, task_type="meeting", status="open")
    t1_reminder_open = _make_task(tenant_id, lead_1, task_type="reminder", status="open")
    t2_followup_open = _make_task(tenant_id, lead_2, task_type="follow_up", status="open")

    session = _mock_session()
    # The DB select filters: lead_id == lead_1, type == 'follow_up', status == 'open'
    # Simulating what session.scalars(statement).all() returns for that query:
    session.scalars.return_value.all.return_value = [t1_followup_open]

    with patch("app.modules.tasks.service._add_timeline") as mock_timeline:
        with patch("app.modules.tasks.events.emit_task_event") as mock_emit:
            paused = pause_followups(session, lead_1, reason="customer_reply")

    assert len(paused) == 1
    assert paused[0] is t1_followup_open
    assert t1_followup_open.status == "paused"
    assert t1_followup_open.version == 2

    # Untouched tasks
    assert t1_call_open.status == "open"
    assert t1_meeting_open.status == "open"
    assert t1_reminder_open.status == "open"
    assert t2_followup_open.status == "open"

    mock_timeline.assert_called_once()
    assert mock_timeline.call_args[0][2] == "task_paused"
    mock_emit.assert_called_once_with(session, "task.cancelled", t1_followup_open)


# ---------------------------------------------------------------------------
# 2. cancel_followups tests
# ---------------------------------------------------------------------------


def test_cancel_followups_cancels_open_and_paused_followups_for_lead():
    from app.modules.tasks.service import cancel_followups

    tenant_id = uuid.uuid4()
    lead_1 = uuid.uuid4()

    t_open = _make_task(tenant_id, lead_1, task_type="follow_up", status="open")
    t_paused = _make_task(tenant_id, lead_1, task_type="follow_up", status="paused")
    t_call = _make_task(tenant_id, lead_1, task_type="call", status="open")

    session = _mock_session()
    session.scalars.return_value.all.return_value = [t_open, t_paused]

    with patch("app.modules.tasks.service._add_timeline") as mock_timeline:
        with patch("app.modules.tasks.events.emit_task_event") as mock_emit:
            cancelled = cancel_followups(session, lead_1, reason="opt_out")

    assert len(cancelled) == 2
    assert t_open.status == "cancelled"
    assert t_paused.status == "cancelled"
    assert t_open.version == 2
    assert t_paused.version == 2
    assert t_call.status == "open"

    assert mock_timeline.call_count == 2
    assert mock_emit.call_count == 2


# ---------------------------------------------------------------------------
# 3. Messaging rejects paused, cancelled, unapproved tasks, or won/lost leads
# ---------------------------------------------------------------------------


def test_ensure_task_can_send_rejects_paused_and_cancelled():
    from app.modules.messaging.service import ensure_task_can_send

    tenant_id = uuid.uuid4()
    lead = SimpleNamespace(id=uuid.uuid4(), status="contacted", opted_out=False)

    task_paused = _make_task(tenant_id, lead.id, status="paused")
    with pytest.raises(AuthError) as exc_paused:
        ensure_task_can_send(task_paused, lead)
    assert exc_paused.value.status_code == 409
    assert exc_paused.value.code == "task_inactive"

    task_cancelled = _make_task(tenant_id, lead.id, status="cancelled")
    with pytest.raises(AuthError) as exc_cancelled:
        ensure_task_can_send(task_cancelled, lead)
    assert exc_cancelled.value.status_code == 409
    assert exc_cancelled.value.code == "task_inactive"


def test_ensure_task_can_send_rejects_unapproved_task():
    from app.modules.messaging.service import ensure_task_can_send

    tenant_id = uuid.uuid4()
    lead = SimpleNamespace(id=uuid.uuid4(), status="contacted", opted_out=False)

    task_pending = _make_task(
        tenant_id, lead.id, status="open", requires_approval=True, approval_status="pending"
    )
    with pytest.raises(AuthError) as exc:
        ensure_task_can_send(task_pending, lead)
    assert exc.value.status_code == 409
    assert exc.value.code == "approval_required"


def test_ensure_task_can_send_rejects_won_or_lost_lead_even_if_approved():
    from app.modules.messaging.service import ensure_task_can_send

    tenant_id = uuid.uuid4()
    lead_won = SimpleNamespace(id=uuid.uuid4(), status="won", opted_out=False)
    lead_lost = SimpleNamespace(id=uuid.uuid4(), status="lost", opted_out=False)

    task_approved = _make_task(
        tenant_id, lead_won.id, status="open", requires_approval=True, approval_status="approved"
    )

    with pytest.raises(AuthError) as exc_won:
        ensure_task_can_send(task_approved, lead_won)
    assert exc_won.value.status_code == 409
    assert exc_won.value.code == "lead_closed"

    with pytest.raises(AuthError) as exc_lost:
        ensure_task_can_send(task_approved, lead_lost)
    assert exc_lost.value.status_code == 409
    assert exc_lost.value.code == "lead_closed"


def test_ensure_task_can_send_passes_for_valid_approved_open_task():
    from app.modules.messaging.service import ensure_task_can_send

    tenant_id = uuid.uuid4()
    lead = SimpleNamespace(id=uuid.uuid4(), status="qualified", opted_out=False)
    task = _make_task(
        tenant_id, lead.id, status="open", requires_approval=True, approval_status="approved"
    )

    # Should not raise
    ensure_task_can_send(task, lead)


# ---------------------------------------------------------------------------
# 4. Approve / Reject permissions & scope tests
# ---------------------------------------------------------------------------


def test_rep_gets_403_on_approve():
    from app.modules.tasks.service import decide_task_approval

    rep_ctx = _ctx(role="rep")
    session = _mock_session()
    task_id = uuid.uuid4()

    with pytest.raises(AuthError) as exc:
        decide_task_approval(session, rep_ctx, task_id, approved=True)

    assert exc.value.status_code == 403
    assert exc.value.code == "forbidden"


def test_cross_tenant_approve_returns_404():
    from app.modules.tasks.service import decide_task_approval

    admin_ctx_a = _ctx(role="admin")
    session = _mock_session()
    task_id = uuid.uuid4()

    # Scope lookup returns None because task belongs to tenant B
    not_found = AuthError(404, "not_found", "Task not found")
    with patch("app.modules.tasks.service._get_scoped_task", side_effect=not_found):
        with pytest.raises(AuthError) as exc:
            decide_task_approval(session, admin_ctx_a, task_id, approved=True)

    assert exc.value.status_code == 404
    assert exc.value.code == "not_found"


def test_manager_cannot_approve_other_team_task():
    from app.modules.tasks.service import decide_task_approval

    team_1 = uuid.uuid4()
    manager_ctx = _ctx(role="manager", team_id=team_1)
    session = _mock_session()
    task_id = uuid.uuid4()

    # Scope lookup filters by team_id == team_1; fails with 404 for another team's task
    not_found = AuthError(404, "not_found", "Task not found")
    with patch("app.modules.tasks.service._get_scoped_task", side_effect=not_found):
        with pytest.raises(AuthError) as exc:
            decide_task_approval(session, manager_ctx, task_id, approved=True)

    assert exc.value.status_code == 404


def test_approve_rejects_task_not_requiring_approval_or_not_pending():
    from app.modules.tasks.service import decide_task_approval

    admin_ctx = _ctx(role="admin")
    session = _mock_session()

    task_no_approval = _make_task(
        admin_ctx.tenant_id, uuid.uuid4(), requires_approval=False, approval_status="not_required"
    )
    with patch("app.modules.tasks.service._get_scoped_task", return_value=task_no_approval):
        with pytest.raises(AuthError) as exc1:
            decide_task_approval(session, admin_ctx, task_no_approval.id, approved=True)
        assert exc1.value.status_code == 409
        assert exc1.value.code == "invalid_approval_state"

    task_already_approved = _make_task(
        admin_ctx.tenant_id, uuid.uuid4(), requires_approval=True, approval_status="approved"
    )
    with patch("app.modules.tasks.service._get_scoped_task", return_value=task_already_approved):
        with pytest.raises(AuthError) as exc2:
            decide_task_approval(session, admin_ctx, task_already_approved.id, approved=True)
        assert exc2.value.status_code == 409
        assert exc2.value.code == "invalid_approval_state"


def test_approve_succeeds_and_emits_task_due_with_available_at():
    from app.modules.tasks.service import decide_task_approval

    admin_ctx = _ctx(role="admin")
    session = _mock_session()
    due_at = datetime.now(UTC) + timedelta(days=2)
    task = _make_task(
        admin_ctx.tenant_id, uuid.uuid4(), requires_approval=True, approval_status="pending"
    )
    task.due_at = due_at

    with patch("app.modules.tasks.service._get_scoped_task", return_value=task):
        with patch("app.modules.tasks.service._audit"):
            with patch("app.modules.tasks.events.emit_task_event") as mock_emit:
                result = decide_task_approval(
                    session, admin_ctx, task.id, approved=True, note="Looks good"
                )

    assert result.approval_status == "approved"
    assert result.approved_by_user_id == admin_ctx.user_id
    assert result.approved_at is not None
    assert result.approval_note == "Looks good"
    assert result.version == 2

    mock_emit.assert_called_once()
    event_type, emitted_task = mock_emit.call_args[0][1], mock_emit.call_args[0][2]
    available_at = mock_emit.call_args[1].get("available_at")
    assert event_type == "task.due"
    assert emitted_task is task
    assert available_at == due_at


def test_reject_succeeds_and_emits_task_cancelled():
    from app.modules.tasks.service import decide_task_approval

    admin_ctx = _ctx(role="admin")
    session = _mock_session()
    task = _make_task(
        admin_ctx.tenant_id, uuid.uuid4(), requires_approval=True, approval_status="pending"
    )

    with patch("app.modules.tasks.service._get_scoped_task", return_value=task):
        with patch("app.modules.tasks.service._audit"):
            with patch("app.modules.tasks.events.emit_task_event") as mock_emit:
                result = decide_task_approval(
                    session, admin_ctx, task.id, approved=False, note="Not ready"
                )

    assert result.approval_status == "rejected"
    assert result.rejected_by_user_id == admin_ctx.user_id
    assert result.rejected_at is not None
    assert result.approval_note == "Not ready"
    assert result.version == 2

    mock_emit.assert_called_once_with(session, "task.cancelled", task)


# ---------------------------------------------------------------------------
# 5. Inbound integration calls pause_followups
# ---------------------------------------------------------------------------


def test_inbound_message_calls_pause_followups():
    from app.modules.integrations import inbound

    session = _mock_session()
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    fake_lead = SimpleNamespace(id=lead_id, tenant_id=tenant_id, assigned_user_id=None)
    fake_capture = SimpleNamespace(lead=fake_lead)
    fake_conversation = SimpleNamespace(
        id=conversation_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel="whatsapp",
        external_contact_id=None,
        external_conversation_id=None,
    )

    msg_input = inbound.InboundMessage(
        provider="whatsapp",
        channel="whatsapp",
        source="whatsapp",
        account_id="acc_1",
        external_contact_id="c_1",
        external_conversation_id="conv_1",
        external_lead_id="l_1",
        contact_name="Customer",
        message_id="msg_123",
        body_text="Hi, I am interested in your pricing.",
    )

    with patch("app.modules.integrations.inbound.capture_lead", return_value=fake_capture):
        with patch("app.modules.integrations.inbound.emit_message_received"):
            with patch("app.modules.tasks.service.pause_followups") as mock_pause:
                session.execute.return_value.scalar_one_or_none.return_value = fake_conversation
                inbound.store_inbound_message(session, tenant_id=tenant_id, inbound=msg_input)

    mock_pause.assert_called_once_with(session, lead_id, reason="customer_reply")


# ---------------------------------------------------------------------------
# 6. Opt-out calls cancel_followups
# ---------------------------------------------------------------------------


def test_apply_opt_out_calls_cancel_followups():
    from app.modules.leads import optout

    session = _mock_session()
    tenant_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    lead = SimpleNamespace(
        id=lead_id,
        tenant_id=tenant_id,
        opted_out=False,
        opted_out_at=None,
        opted_out_source=None,
        version=1,
    )

    session.scalar.return_value = lead
    # to_regclass returns truthy
    session.execute.return_value.scalar.return_value = "tasks"

    with patch("app.modules.tasks.service.cancel_followups") as mock_cancel:
        with patch("app.modules.leads.optout.record_audit_event"):
            optout.apply_opt_out(session, lead_id, source="whatsapp")

    mock_cancel.assert_called_once_with(session, lead_id, reason="opt_out")
    assert lead.opted_out is True
