"""Tests for internal automation endpoints (/internal/v1/automation).

Offline testing without live n8n instance.
"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.core.service_auth import (
    build_signature,
    canonical_request,
)
from app.database.session import get_session
from app.main import app
from app.modules.conversations.models import Conversation
from app.modules.leads.models import Lead
from app.modules.tasks.models import Task

SECRET = "test-automation-service-secret"


def make_signed_request(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    tenant_id: str | None = None,
    service_id: str = "n8n",
    idempotency_key: str = "auto-action-12345",
    timestamp: str | None = None,
    secret: str = SECRET,
    tamper_signature: bool = False,
):
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else b""
    t_id = tenant_id or str(uuid.uuid4())
    ts = timestamp or str(int(time.time()))
    headers = {
        "X-Service-Id": service_id,
        "X-Tenant-ID": t_id,
        "X-Timestamp": ts,
        "X-Idempotency-Key": idempotency_key,
    }
    canonical = canonical_request(
        service_id=headers["X-Service-Id"],
        tenant_id=headers["X-Tenant-ID"],
        method=method,
        path=path,
        timestamp=headers["X-Timestamp"],
        idempotency_key=headers["X-Idempotency-Key"],
        raw_body=raw_body,
    )
    sig = build_signature(secret, canonical)
    if tamper_signature:
        sig = sig[:-4] + "0000"
    headers["X-Signature"] = sig
    return raw_body, headers


def setup_test_app(monkeypatch):
    mock_session = MagicMock()
    monkeypatch.setattr(settings, "n8n_service_secret", SecretStr(SECRET))
    monkeypatch.setitem(app.dependency_overrides, get_session, lambda: mock_session)
    client = TestClient(app)
    return client, mock_session


def test_internal_health_mounted(monkeypatch):
    client, _ = setup_test_app(monkeypatch)
    path = "/internal/v1/automation/health"
    raw_body, headers = make_signed_request("GET", path)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"
    assert resp.json()["data"]["service"] == "n8n"


def test_reject_bad_hmac_401(monkeypatch):
    client, _ = setup_test_app(monkeypatch)
    path = "/internal/v1/automation/health"
    raw_body, headers = make_signed_request("GET", path, tamper_signature=True)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_reject_timestamp_skew_401(monkeypatch):
    client, _ = setup_test_app(monkeypatch)
    path = "/internal/v1/automation/health"
    old_ts = str(int(time.time()) - 350)
    raw_body, headers = make_signed_request("GET", path, timestamp=old_ts)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 401


def test_get_lead_context_returns_no_pii(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    lead_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = f"/internal/v1/automation/leads/{lead_id}"

    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="John Doe",
        email="john@example.com",
        phone="+8801711111111",
        status="contacted",
        assigned_user_id=uuid.uuid4(),
        team_id=uuid.uuid4(),
        opted_out=False,
    )
    session.scalar.return_value = lead

    raw_body, headers = make_signed_request("GET", path, tenant_id=str(tenant_id))
    resp = client.get(path, headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == str(lead_id)
    assert data["name"] == "John Doe"
    assert data["status"] == "contacted"
    assert data["assigned_user_id"] == str(lead.assigned_user_id)
    assert data["team_id"] == str(lead.team_id)
    assert data["opted_out"] is False
    # Verify NO contact details are returned
    assert "email" not in data
    assert "phone" not in data


def test_cross_tenant_resource_returns_404_not_403(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    lead_id = uuid.uuid4()
    tenant_a = uuid.uuid4()
    path = f"/internal/v1/automation/leads/{lead_id}"

    # Lead belongs to tenant B; session lookup with tenant A returns None
    session.scalar.return_value = None

    raw_body, headers = make_signed_request("GET", path, tenant_id=str(tenant_a))
    resp = client.get(path, headers=headers)

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_post_lead_assess_missing_requests_assessment(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    lead_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = f"/internal/v1/automation/leads/{lead_id}/assess"

    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="Lead Test",
        status="new",
        source="website_form",
    )
    # Lead exists, no existing assessment
    session.scalar.side_effect = [lead, None]

    with (
        patch("app.modules.automation.service.enqueue_event") as mock_enqueue,
        patch(
            "app.modules.automation.service.claim_idempotency",
            return_value=(uuid.uuid4(), None),
        ),
        patch("app.modules.automation.service.store_idempotency_response"),
    ):
        raw_body, headers = make_signed_request("POST", path, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 202
        assert resp.json()["data"]["status"] == "requested"
        mock_enqueue.assert_called_once()


def test_post_lead_assess_already_satisfied(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    lead_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = f"/internal/v1/automation/leads/{lead_id}/assess"

    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="Lead Test",
        status="new",
    )
    existing_assessment = MagicMock()
    existing_assessment.id = uuid.uuid4()
    existing_assessment.status = "ok"

    # Lead exists, assessment exists and is ok
    session.scalar.side_effect = [lead, existing_assessment]

    with (
        patch("app.modules.automation.service.enqueue_event") as mock_enqueue,
        patch(
            "app.modules.automation.service.claim_idempotency",
            return_value=(uuid.uuid4(), None),
        ),
        patch("app.modules.automation.service.store_idempotency_response"),
    ):
        raw_body, headers = make_signed_request("POST", path, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "satisfied"
        mock_enqueue.assert_not_called()


def test_send_message_quiet_hours_reschedules_task(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    conv_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    task_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = "/internal/v1/automation/messages"

    conv = Conversation(
        id=conv_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel="whatsapp",
    )
    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="Jane",
        phone="+8801700000000",
        consent=True,
        opted_out=False,
        status="contacted",
    )
    task = Task(
        id=task_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        status="open",
        requires_approval=False,
    )

    session.scalar.side_effect = [conv, lead, task]

    reschedule_time = datetime.now(UTC) + timedelta(hours=10)

    with (
        patch(
            "app.modules.automation.service.claim_idempotency",
            return_value=(uuid.uuid4(), None),
        ),
        patch("app.modules.automation.service.store_idempotency_response"),
        patch(
            "app.modules.automation.service.is_quiet_hours",
            return_value=(True, reschedule_time),
        ),
        patch("app.modules.automation.service.cancel_pending_task_due") as mock_cancel,
        patch("app.modules.automation.service.emit_task_event") as mock_emit,
    ):
        body = {
            "conversation_id": str(conv_id),
            "text": "Hello there",
            "task_id": str(task_id),
        }
        raw_body, headers = make_signed_request("POST", path, body, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 202
        assert resp.json()["data"]["status"] == "rescheduled"
        assert resp.json()["data"]["reason"] == "quiet_hours"
        mock_cancel.assert_called_once()
        mock_emit.assert_called_once()


def test_send_message_rejects_paused_task(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    conv_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    task_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = "/internal/v1/automation/messages"

    conv = Conversation(
        id=conv_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel="whatsapp",
    )
    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="Jane",
        consent=True,
        opted_out=False,
        status="contacted",
    )
    task = Task(
        id=task_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        status="paused",
    )

    session.scalar.side_effect = [conv, lead, task]

    with patch(
        "app.modules.automation.service.claim_idempotency",
        return_value=(uuid.uuid4(), None),
    ):
        body = {
            "conversation_id": str(conv_id),
            "text": "Hello",
            "task_id": str(task_id),
        }
        raw_body, headers = make_signed_request("POST", path, body, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "task_inactive"


def test_send_message_rejects_opted_out_lead(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    conv_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = "/internal/v1/automation/messages"

    conv = Conversation(
        id=conv_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel="whatsapp",
    )
    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="Jane",
        consent=True,
        opted_out=True,
        status="contacted",
    )

    session.scalar.side_effect = [conv, lead]

    with patch(
        "app.modules.automation.service.claim_idempotency",
        return_value=(uuid.uuid4(), None),
    ):
        body = {"conversation_id": str(conv_id), "text": "Hello"}
        raw_body, headers = make_signed_request("POST", path, body, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code in (403, 409)
        assert resp.json()["error"]["code"] == "opted_out"


def test_send_message_rejects_no_consent(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    conv_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = "/internal/v1/automation/messages"

    conv = Conversation(
        id=conv_id,
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel="whatsapp",
    )
    lead = Lead(
        id=lead_id,
        tenant_id=tenant_id,
        name="Jane",
        consent=False,
        opted_out=False,
        status="contacted",
    )

    session.scalar.side_effect = [conv, lead]

    with patch(
        "app.modules.automation.service.claim_idempotency",
        return_value=(uuid.uuid4(), None),
    ):
        body = {"conversation_id": str(conv_id), "text": "Hello"}
        raw_body, headers = make_signed_request("POST", path, body, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "consent_required"


def test_task_result_failed_retryable_emits_task_due(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    task_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = f"/internal/v1/automation/tasks/{task_id}/result"

    task = Task(
        id=task_id,
        tenant_id=tenant_id,
        lead_id=uuid.uuid4(),
        status="open",
    )
    session.scalar.return_value = task

    with (
        patch(
            "app.modules.automation.service.claim_idempotency",
            return_value=(uuid.uuid4(), None),
        ),
        patch("app.modules.automation.service.store_idempotency_response"),
        patch("app.modules.automation.service.cancel_pending_task_due") as mock_cancel,
        patch("app.modules.automation.service.emit_task_event") as mock_emit,
    ):
        body = {
            "status": "failed",
            "retryable": True,
            "error_code": "network_timeout",
        }
        raw_body, headers = make_signed_request("POST", path, body, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "failed"
        mock_cancel.assert_called_once()
        mock_emit.assert_called_once()
        # Verify available_at is roughly 10 minutes in the future
        args, kwargs = mock_emit.call_args
        available_at = kwargs.get("available_at")
        assert available_at is not None
        diff = available_at - datetime.now(UTC)
        assert 500 < diff.total_seconds() < 700


def test_task_result_sent_done_completes_task(monkeypatch):
    client, session = setup_test_app(monkeypatch)
    task_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    path = f"/internal/v1/automation/tasks/{task_id}/result"

    task = Task(
        id=task_id,
        tenant_id=tenant_id,
        lead_id=uuid.uuid4(),
        status="open",
    )
    session.scalar.return_value = task

    with (
        patch(
            "app.modules.automation.service.claim_idempotency",
            return_value=(uuid.uuid4(), None),
        ),
        patch("app.modules.automation.service.store_idempotency_response"),
        patch("app.modules.automation.service.cancel_pending_task_due") as mock_cancel,
    ):
        body = {
            "status": "sent",
            "task_status": "done",
            "note": "Delivered successfully",
        }
        raw_body, headers = make_signed_request("POST", path, body, tenant_id=str(tenant_id))
        resp = client.post(path, content=raw_body, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "sent"
        assert task.status == "done"
        assert task.completed_at is not None
        mock_cancel.assert_called_once()
