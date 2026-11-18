"""Unit tests for /internal/v1/automation/errors endpoint (#14)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core.service_auth import InternalServiceContext
from app.modules.automation.schemas import AutomationErrorRequest
from app.modules.automation.service import record_automation_error


def test_automation_error_schema_validation():
    req = AutomationErrorRequest(
        workflow_id="wf-123",
        workflow_name="Follow-up",
        node_name="Send WhatsApp",
        error_class="HTTPError",
        error_message="Connection timed out",
    )
    assert req.workflow_id == "wf-123"
    assert req.error_class == "HTTPError"


def test_automation_error_schema_rejects_empty_required_fields():
    with pytest.raises(ValidationError):
        AutomationErrorRequest(workflow_id="", error_class="HTTPError")

    with pytest.raises(ValidationError):
        AutomationErrorRequest(workflow_id="wf-1", error_class="")


def test_record_automation_error_records_audit_event():
    session = MagicMock()
    tenant_id = uuid.uuid4()
    context = InternalServiceContext(
        service_id="n8n",
        tenant_id=tenant_id,
        idempotency_key="err-key-001",
        body_sha256="hash-123",
    )
    payload = AutomationErrorRequest(
        workflow_id="wf-456",
        workflow_name="Workflow B",
        node_name="Dispatch Follow-up Message",
        error_class="ExecutionTimeout",
        error_message="n8n execution timed out after 30s",
    )

    with (
        patch(
            "app.modules.automation.service.claim_idempotency",
            return_value=(uuid.uuid4(), None),
        ),
        patch("app.modules.automation.service.store_idempotency_response") as mock_store,
        patch("app.modules.automation.service.record_audit_event") as mock_audit,
    ):
        status_code, resp = record_automation_error(session, context, payload)

        assert status_code == 202
        assert resp == {"data": {"status": "recorded"}}
        mock_audit.assert_called_once_with(
            session,
            action="automation.error",
            actor_type="automation",
            tenant_id=tenant_id,
            entity_type="workflow",
            details={
                "workflow_id": "wf-456",
                "workflow_name": "Workflow B",
                "node_name": "Dispatch Follow-up Message",
                "error_class": "ExecutionTimeout",
                "error_message": "n8n execution timed out after 30s",
            },
        )
        mock_store.assert_called_once()
        session.commit.assert_called_once()


def test_record_automation_error_idempotent_replay():
    session = MagicMock()
    tenant_id = uuid.uuid4()
    context = InternalServiceContext(
        service_id="n8n",
        tenant_id=tenant_id,
        idempotency_key="err-key-001",
        body_sha256="hash-123",
    )
    payload = AutomationErrorRequest(
        workflow_id="wf-456",
        error_class="ExecutionTimeout",
    )

    replayed = {"data": {"status": "recorded", "replayed": True}}
    with (
        patch("app.modules.automation.service.claim_idempotency", return_value=(None, replayed)),
        patch("app.modules.automation.service.record_audit_event") as mock_audit,
    ):
        status_code, resp = record_automation_error(session, context, payload)

        assert status_code == 202
        assert resp == replayed
        mock_audit.assert_not_called()
        session.commit.assert_not_called()
