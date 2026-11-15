import json
import time
import uuid

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.core.service_auth import (
    MAX_INTERNAL_BODY_BYTES,
    build_signature,
    canonical_request,
)
from app.database.session import get_session
from app.main import app
from app.modules.notifications import service

SECRET = "test-notification-service-secret"
PATH = "/internal/v1/automation/notifications"


def make_request_body(**updates):
    value = {
        "user_id": str(uuid.uuid4()),
        "type": "new_lead",
        "title": "New lead",
        "body": "A new lead is assigned to you.",
        "entity_type": "lead",
        "entity_id": str(uuid.uuid4()),
    }
    value.update(updates)
    return value


def signed_request(body, *, path=PATH, key="notification-action-1", **overrides):
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    headers = {
        "X-Service-Id": "n8n",
        "X-Tenant-ID": str(uuid.uuid4()),
        "X-Timestamp": timestamp,
        "X-Idempotency-Key": key,
    }
    headers.update(overrides)
    canonical = canonical_request(
        service_id=headers["X-Service-Id"],
        tenant_id=headers["X-Tenant-ID"],
        method="POST",
        path=path,
        timestamp=headers["X-Timestamp"],
        idempotency_key=headers["X-Idempotency-Key"],
        raw_body=raw_body,
    )
    headers["X-Signature"] = build_signature(SECRET, canonical)
    return raw_body, headers


def setup_client(monkeypatch):
    session = object()
    monkeypatch.setattr(settings, "n8n_service_secret", SecretStr(SECRET))
    monkeypatch.setitem(app.dependency_overrides, get_session, lambda: session)
    return TestClient(app), session


def _noop_create(*_args):
    return None


def test_notification_endpoint_returns_empty_202(monkeypatch):
    client, session = setup_client(monkeypatch)
    created = []
    monkeypatch.setattr(
        service,
        "create_notification",
        lambda passed_session, context, payload: created.append((passed_session, context, payload)),
    )
    body = make_request_body()
    raw_body, headers = signed_request(body)

    response = client.post(PATH, content=raw_body, headers=headers)

    assert response.status_code == 202
    assert response.content == b""
    assert created[0][0] is session
    assert created[0][1].tenant_id == uuid.UUID(headers["X-Tenant-ID"])
    assert created[0][2].user_id == uuid.UUID(body["user_id"])


def test_notification_endpoint_rejects_invalid_hmac(monkeypatch):
    client, _ = setup_client(monkeypatch)
    monkeypatch.setattr(service, "create_notification", _noop_create)
    raw_body, headers = signed_request(make_request_body())
    headers["X-Tenant-ID"] = str(uuid.uuid4())

    response = client.post(PATH, content=raw_body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_notification_endpoint_rejects_oversized_body_before_auth(monkeypatch):
    client, _ = setup_client(monkeypatch)
    response = client.post(PATH, content=b"x" * (MAX_INTERNAL_BODY_BYTES + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_notification_endpoint_validates_body_after_authentication(monkeypatch):
    client, _ = setup_client(monkeypatch)
    monkeypatch.setattr(service, "create_notification", _noop_create)
    body = make_request_body(type="message_received")
    raw_body, headers = signed_request(body)

    response = client.post(PATH, content=raw_body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_notification_endpoint_is_registered():
    assert PATH in app.openapi()["paths"]
