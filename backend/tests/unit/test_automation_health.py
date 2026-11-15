"""The internal health endpoint accepts a correctly signed request and nothing else."""

import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.core.service_auth import build_signature, canonical_request
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.automation.router import router

SECRET = "s" * 40
TENANT = str(uuid.uuid4())
PATH = "/internal/v1/automation/health"


@pytest.fixture(autouse=True)
def configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "n8n_service_secret", SecretStr(SECRET))


@pytest.fixture
def client():
    app = FastAPI()
    app.add_exception_handler(AuthError, auth_error_handler)
    app.include_router(router)
    return TestClient(app)


def signed_headers(*, method="GET", path=PATH, body=b"", secret=SECRET, timestamp=None):
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    key = uuid.uuid4().hex
    canonical = canonical_request(
        service_id="n8n",
        tenant_id=TENANT,
        method=method,
        path=path,
        timestamp=stamp,
        idempotency_key=key,
        raw_body=body,
    )
    return {
        "X-Service-Id": "n8n",
        "X-Tenant-ID": TENANT,
        "X-Timestamp": stamp,
        "X-Idempotency-Key": key,
        "X-Signature": build_signature(secret, canonical),
    }


def test_signed_request_is_accepted(client):
    response = client.get(PATH, headers=signed_headers())

    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok", "service": "n8n"}}


def test_request_without_headers_is_rejected(client):
    assert client.get(PATH).status_code == 401


def test_wrong_secret_is_rejected(client):
    response = client.get(PATH, headers=signed_headers(secret="x" * 40))

    assert response.status_code == 401


def test_signature_for_another_path_is_rejected(client):
    other = signed_headers(path="/internal/v1/automation/notifications")

    assert client.get(PATH, headers=other).status_code == 401


def test_stale_timestamp_is_rejected(client):
    response = client.get(PATH, headers=signed_headers(timestamp=int(time.time()) - 3600))

    assert response.status_code == 401