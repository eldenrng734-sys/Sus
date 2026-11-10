import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.core.tenancy import TenantContext, get_tenant_context
from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError


def _fake_session():
    # These tests fail before any database work, so no real session is needed.
    yield None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 48)
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)

    @mini.get("/ctx")
    def ctx(c: TenantContext = Depends(get_tenant_context)) -> dict:
        return {"role": c.role}

    mini.dependency_overrides[get_session] = _fake_session
    return TestClient(mini)


def _bearer() -> dict:
    token = create_access_token(uuid.uuid4(), uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_is_401(client):
    r = client.get("/ctx", headers={"X-Tenant-ID": str(uuid.uuid4())})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_garbage_token_is_401(client):
    headers = {"Authorization": "Bearer not-a-token", "X-Tenant-ID": str(uuid.uuid4())}
    assert client.get("/ctx", headers=headers).status_code == 401


def test_missing_tenant_header_is_400(client):
    r = client.get("/ctx", headers=_bearer())
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_malformed_tenant_header_is_400(client):
    r = client.get("/ctx", headers={**_bearer(), "X-Tenant-ID": "not-a-uuid"})
    assert r.status_code == 400


def test_tenant_id_in_query_string_is_ignored(client):
    # A tenant_id in the URL must never be accepted as the tenant.
    r = client.get(f"/ctx?tenant_id={uuid.uuid4()}", headers=_bearer())
    assert r.status_code == 400
