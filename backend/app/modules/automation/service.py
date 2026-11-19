import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.idempotency import claim_idempotency, store_idempotency_response
from app.core.outbox import enqueue_event
from app.core.service_auth import InternalServiceContext
from app.database.session import set_tenant_context
from app.modules.ai.models import LeadAssessment
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation
from app.modules.leads.models import Lead
from app.modules.messaging.service import (
    _deliver,
    _queue_message,
    _resolve_credentials,
    _status_session,
    build_text_payload,
    ensure_e164_phone,
    ensure_task_can_send,
    ensure_whatsapp_conversation,
    ensure_window_open,
)
from app.modules.settings.service import is_quiet_hours
from app.modules.tasks.events import cancel_pending_task_due, emit_task_event
from app.modules.tasks.models import Task

from .schemas import (
    AutomationErrorRequest,
    AutomationMessageSendRequest,
    TaskResultRequest,
)


def get_lead_context(
    session: Session,
    context: InternalServiceContext,
    lead_id: uuid.UUID,
) -> dict:
    set_tenant_context(session, str(context.tenant_id))
    lead = session.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.tenant_id == context.tenant_id,
        )
    )
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")

    manager_user_ids: list[str] = []
    if lead.assigned_user_id is None:
        from app.modules.tenants.models import TenantMembership
        from app.modules.users.models import User

        mgr_query = (
            select(TenantMembership.user_id)
            .join(User, User.id == TenantMembership.user_id)
            .where(
                TenantMembership.tenant_id == context.tenant_id,
                TenantMembership.role == "manager",
                TenantMembership.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
        if lead.team_id is not None:
            mgr_query = mgr_query.where(
                (TenantMembership.team_id == lead.team_id) | (TenantMembership.team_id.is_(None))
            )
        manager_user_ids = [str(uid) for uid in session.scalars(mgr_query).all()]

    return {
        "id": str(lead.id),
        "name": lead.name,
        "status": lead.status,
        "assigned_user_id": str(lead.assigned_user_id) if lead.assigned_user_id else None,
        "team_id": str(lead.team_id) if lead.team_id else None,
        "opted_out": lead.opted_out,
        "manager_user_ids": manager_user_ids,
    }


def request_lead_assessment(
    session: Session,
    context: InternalServiceContext,
    lead_id: uuid.UUID,
) -> tuple[int, dict]:
    set_tenant_context(session, str(context.tenant_id))
    path = f"/internal/v1/automation/leads/{lead_id}/assess"

    idempotency_id, replay_body = claim_idempotency(
        session,
        tenant_id=context.tenant_id,
        user_id=context.service_id,
        path=path,
        key=context.idempotency_key,
        request_hash=context.body_sha256,
        caller_type="service",
    )
    if replay_body is not None:
        return 200, replay_body

    lead = session.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.tenant_id == context.tenant_id,
        )
    )
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")

    latest_assessment = session.scalar(
        select(LeadAssessment)
        .where(
            LeadAssessment.tenant_id == context.tenant_id,
            LeadAssessment.lead_id == lead_id,
        )
        .order_by(LeadAssessment.created_at.desc())
        .limit(1)
    )

    if latest_assessment is not None and latest_assessment.status != "failed":
        response_data = {
            "data": {
                "status": "satisfied",
                "lead_id": str(lead_id),
                "assessment_id": str(latest_assessment.id),
            }
        }
        if idempotency_id:
            store_idempotency_response(session, idempotency_id, response_data, response_status=200)
        session.commit()
        return 200, response_data

    enqueue_event(
        session,
        tenant_id=context.tenant_id,
        event_type="assessment.requested",
        aggregate_type="lead",
        aggregate_id=lead_id,
        idempotency_key=str(uuid.uuid4()),
        payload={"lead_id": str(lead_id), "source": getattr(lead, "source", "manual")},
    )

    response_data = {
        "data": {
            "status": "requested",
            "lead_id": str(lead_id),
        }
    }
    if idempotency_id:
        store_idempotency_response(session, idempotency_id, response_data, response_status=202)
    session.commit()
    return 202, response_data


async def send_automation_message(
    session: Session,
    context: InternalServiceContext,
    payload: AutomationMessageSendRequest,
) -> tuple[int, dict]:
    set_tenant_context(session, str(context.tenant_id))
    path = "/internal/v1/automation/messages"

    idempotency_id, replay_body = claim_idempotency(
        session,
        tenant_id=context.tenant_id,
        user_id=context.service_id,
        path=path,
        key=context.idempotency_key,
        request_hash=context.body_sha256,
        caller_type="service",
    )
    if replay_body is not None:
        return 202, replay_body

    task_id = payload.task_id or payload.approval_task_id
    conversation = None
    lead = None
    task = None

    if payload.conversation_id is not None:
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.tenant_id == context.tenant_id,
            )
        )
        if conversation is None:
            raise AuthError(404, "not_found", "Conversation not found")
        lead = session.scalar(
            select(Lead).where(
                Lead.id == conversation.lead_id,
                Lead.tenant_id == context.tenant_id,
            )
        )
        if lead is None:
            raise AuthError(404, "not_found", "Lead not found")
        if task_id is not None:
            task = session.scalar(
                select(Task).where(
                    Task.id == task_id,
                    Task.tenant_id == context.tenant_id,
                )
            )
            if task is None or task.lead_id != lead.id:
                raise AuthError(404, "not_found", "Task not found")
    elif task_id is not None:
        task = session.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.tenant_id == context.tenant_id,
            )
        )
        if task is None:
            raise AuthError(404, "not_found", "Task not found")
        lead = session.scalar(
            select(Lead).where(
                Lead.id == task.lead_id,
                Lead.tenant_id == context.tenant_id,
            )
        )
        if lead is None:
            raise AuthError(404, "not_found", "Lead not found")
        conversation = session.scalar(
            select(Conversation)
            .where(
                Conversation.lead_id == lead.id,
                Conversation.tenant_id == context.tenant_id,
                Conversation.channel == "whatsapp",
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        if conversation is None:
            conversation = Conversation(
                tenant_id=context.tenant_id,
                lead_id=lead.id,
                channel="whatsapp",
            )
            session.add(conversation)
            session.flush()
    else:
        raise AuthError(
            422,
            "validation_error",
            "Either conversation_id or task_id must be provided",
        )

    if task is not None:
        ensure_task_can_send(task, lead)

    if lead.status in ("won", "lost"):
        raise AuthError(409, "lead_closed", f"Cannot send message for a {lead.status} lead")

    if lead.opted_out:
        raise AuthError(409, "opted_out", "This lead has opted out of messages")

    if not lead.consent:
        raise AuthError(
            403,
            "consent_required",
            "Lead has not given consent to receive messages",
        )

    in_quiet, window_end_utc = is_quiet_hours(session, context.tenant_id)
    if in_quiet:
        if task is not None and window_end_utc is not None:
            task.due_at = window_end_utc
            cancel_pending_task_due(session, context.tenant_id, task.id, reason="rescheduled")
            emit_task_event(
                session,
                task=task,
                event_type="task.due",
                available_at=window_end_utc,
            )

        reschedule_resp = {
            "data": {
                "status": "rescheduled",
                "reason": "quiet_hours",
                "available_at": window_end_utc.isoformat() if window_end_utc else None,
            }
        }
        if idempotency_id:
            store_idempotency_response(
                session,
                idempotency_id,
                reschedule_resp,
                response_status=202,
            )
        session.commit()
        return 202, reschedule_resp

    ensure_whatsapp_conversation(conversation)
    ensure_window_open(conversation)
    to = ensure_e164_phone(lead)
    token, phone_number_id = _resolve_credentials(session, context.tenant_id)
    msg_text = (
        payload.text
        or (task.notes if task else None)
        or (task.title if task else None)
        or "Following up on your inquiry."
    )
    payload_dict = build_text_payload(msg_text)

    queued, replay = _queue_message(
        session,
        conversation=conversation,
        text=msg_text,
        idempotency_key=context.idempotency_key,
    )
    if replay:
        resp = {"data": {"status": "sent", "message_id": str(queued.id)}}
        return 200, resp

    bind = session.get_bind()
    session.close()

    sent = await _deliver(
        bind=bind,
        tenant_id=context.tenant_id,
        message_id=queued.id,
        to=to,
        payload=payload_dict,
        token=token,
        phone_number_id=phone_number_id,
    )
    result_resp = {"data": {"status": "sent", "message_id": str(sent.id)}}
    with _status_session(bind, context.tenant_id) as status_session:
        store_idempotency_response(status_session, idempotency_id, result_resp, response_status=200)
        status_session.commit()
    return 200, result_resp


def record_task_result(
    session: Session,
    context: InternalServiceContext,
    task_id: uuid.UUID,
    payload: TaskResultRequest,
) -> tuple[int, dict]:
    set_tenant_context(session, str(context.tenant_id))
    path = f"/internal/v1/automation/tasks/{task_id}/result"

    idempotency_id, replay_body = claim_idempotency(
        session,
        tenant_id=context.tenant_id,
        user_id=context.service_id,
        path=path,
        key=context.idempotency_key,
        request_hash=context.body_sha256,
        caller_type="service",
    )
    if replay_body is not None:
        return 200, replay_body

    task = session.scalar(
        select(Task)
        .where(
            Task.id == task_id,
            Task.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if task is None:
        raise AuthError(404, "not_found", "Task not found")

    if payload.status == "sent":
        task.status = payload.task_status or "done"
        if task.status == "done":
            task.completed_at = datetime.now(UTC)
            cancel_pending_task_due(session, context.tenant_id, task.id, reason="completed")
        if payload.note:
            task.notes = f"{task.notes}\n{payload.note}".strip() if task.notes else payload.note
    elif payload.status == "failed":
        if payload.retryable:
            retry_at = datetime.now(UTC) + timedelta(minutes=10)
            task.due_at = retry_at
            cancel_pending_task_due(session, context.tenant_id, task.id, reason="retry")
            emit_task_event(
                session,
                task=task,
                event_type="task.due",
                available_at=retry_at,
            )
        else:
            if payload.task_status:
                task.status = payload.task_status
            if payload.note:
                task.notes = f"{task.notes}\n{payload.note}".strip() if task.notes else payload.note
    elif payload.status == "skipped":
        if payload.task_status:
            task.status = payload.task_status
        if payload.note:
            task.notes = f"{task.notes}\n{payload.note}".strip() if task.notes else payload.note
    elif payload.status == "needs_approval":
        task.requires_approval = True
        task.approval_status = "pending"
        if payload.note:
            task.notes = f"{task.notes}\n{payload.note}".strip() if task.notes else payload.note

    result_data = {
        "data": {
            "task_id": str(task.id),
            "status": payload.status,
            "task_status": task.status,
        }
    }
    if idempotency_id:
        store_idempotency_response(session, idempotency_id, result_data, response_status=200)
    session.commit()
    return 200, result_data


def record_automation_error(
    session: Session,
    context: InternalServiceContext,
    payload: AutomationErrorRequest,
) -> tuple[int, dict]:
    set_tenant_context(session, str(context.tenant_id))
    path = "/internal/v1/automation/errors"

    idempotency_id, replay_body = claim_idempotency(
        session,
        tenant_id=context.tenant_id,
        user_id=context.service_id,
        path=path,
        key=context.idempotency_key,
        request_hash=context.body_sha256,
        caller_type="service",
    )
    if replay_body is not None:
        return 202, replay_body

    record_audit_event(
        session,
        action="automation.error",
        actor_type="automation",
        tenant_id=context.tenant_id,
        entity_type="workflow",
        details={
            "workflow_id": payload.workflow_id,
            "workflow_name": payload.workflow_name,
            "node_name": payload.node_name,
            "error_class": payload.error_class,
            "error_message": payload.error_message,
        },
    )

    response_data = {"data": {"status": "recorded"}}
    if idempotency_id:
        store_idempotency_response(session, idempotency_id, response_data, response_status=202)
    session.commit()
    return 202, response_data
