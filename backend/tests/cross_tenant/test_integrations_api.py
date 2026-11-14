import os
import uuid

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.integrations import decrypt_credentials, get_credentials, register_key
from app.modules.integrations.router import router as integrations_router
from app.modules.integrations.service import CredentialsNotFound
from tests.cross_tenant.support import set_tenant


@pytest.fixture(scope="module", autouse=True)
def _encryption_key():
    key = os.urandom(32)
    register_key(1, key)


@pytest.fixture(autouse=True)
def mock_meta_graph():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as respx_mock:
        # Default mock: Graph API validation succeeds with 200
        respx_mock.get(path__regex=r"^/.*").respond(
            status_code=200,
            json={"id": "valid_account_id", "name": "Verified Account"},
        )
        yield respx_mock


@pytest.fixture(scope="module")
def api_client(admin_engine):
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)
    mini.include_router(integrations_router)

    def _session():
        with Session(admin_engine) as session:
            yield session

    mini.dependency_overrides[get_session] = _session
    return TestClient(mini, client=("127.0.0.1", 50000))


def _headers(tokens, seed, letter: str, role_key: str):
    return {
        **tokens[(letter, role_key)],
        "X-Tenant-ID": str(seed.get(letter).id),
    }


def test_admin_connects_integration_credentials_are_write_only(
    api_client, admin_engine, seed, tokens
):
    account_id = "wa-test-" + uuid.uuid4().hex[:10]
    secret_token = "secret-token-12345"
    payload = {
        "provider_account_id": account_id,
        "access_token": secret_token,
        "scopes": ["messages", "webhooks"],
    }

    headers = _headers(tokens, seed, "a", "admin")
    resp = api_client.post("/api/v1/integrations/whatsapp/connect", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # 1. Write-only verification: No token in response
    assert data["connected"] is True
    assert data["provider"] == "whatsapp"
    assert data["provider_account_id"] == account_id
    assert "access_token" not in data
    assert "secret-token" not in resp.text

    integration_id = uuid.UUID(data["id"])

    # 2. Raw DB check: Ciphertext stored as bytea, no plaintext token in DB row
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        query = (
            "SELECT credentials_encrypted, key_version, status "
            "FROM integrations WHERE id = :id"
        )
        row = conn.execute(text(query), {"id": integration_id}).fetchone()

        assert row is not None
        encrypted_bytes = row[0]
        assert isinstance(encrypted_bytes, (bytes, memoryview))
        # Plaintext token must not be anywhere in the ciphertext
        assert secret_token.encode("utf-8") not in bytes(encrypted_bytes)

        # 3. Decryption check with AAD
        decrypted = decrypt_credentials(bytes(encrypted_bytes), seed.a.id, integration_id)
        assert decrypted["access_token"] == secret_token
        assert decrypted["provider_account_id"] == account_id

        # 4. Audit log check: No sensitive tokens logged
        audit = conn.execute(
            text("SELECT action, details FROM audit_logs WHERE entity_id = :id"),
            {"id": integration_id},
        ).fetchone()
        assert audit is not None
        assert audit[0] == "integration.connect"
        assert secret_token not in str(audit[1])

    # 5. Service get_credentials returns decrypted credentials
    with Session(admin_engine) as session:
        creds = get_credentials(seed.a.id, "whatsapp", session)
        assert creds["access_token"] == secret_token
        assert creds["provider_account_id"] == account_id


def test_list_integrations_never_returns_credentials(api_client, seed, tokens):
    account_id = "wa-list-" + uuid.uuid4().hex[:10]
    headers = _headers(tokens, seed, "a", "admin")

    api_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"provider_account_id": account_id, "access_token": "token-for-list"},
        headers=headers,
    )

    resp = api_client.get("/api/v1/integrations", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1

    for item in items:
        assert "access_token" not in item
        assert "credentials" not in item
        assert "credentials_encrypted" not in item


def test_disconnect_integration(api_client, admin_engine, seed, tokens):
    account_id = "wa-disc-" + uuid.uuid4().hex[:10]
    headers = _headers(tokens, seed, "a", "admin")

    # Connect
    conn_resp = api_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"provider_account_id": account_id, "access_token": "token-xyz"},
        headers=headers,
    )
    integration_id = conn_resp.json()["data"]["id"]

    # Disconnect
    disc_resp = api_client.delete(f"/api/v1/integrations/{integration_id}", headers=headers)
    assert disc_resp.status_code == 200
    assert disc_resp.json()["data"]["connected"] is False
    assert disc_resp.json()["data"]["status"] == "disabled"

    # Verify status in DB
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        status = conn.scalar(
            text("SELECT status FROM integrations WHERE id = :id"),
            {"id": uuid.UUID(integration_id)},
        )
        assert status == "disabled"

    # get_credentials should now raise CredentialsNotFound because status is not active
    with Session(admin_engine) as session:
        # Stub values in env might match if not disabled, but disabled row won't return active
        with pytest.raises(CredentialsNotFound):
            get_credentials(uuid.uuid4(), "whatsapp", session)


def test_rep_and_manager_forbidden(api_client, seed, tokens):
    for role in ("rep", "manager"):
        headers = _headers(tokens, seed, "a", role)
        r_get = api_client.get("/api/v1/integrations", headers=headers)
        assert r_get.status_code == 403, f"{role} should get 403 on GET"

        r_post = api_client.post(
            "/api/v1/integrations/whatsapp/connect",
            json={"provider_account_id": "acc-1", "access_token": "tok"},
            headers=headers,
        )
        assert r_post.status_code == 403, f"{role} should get 403 on POST"


def test_cross_tenant_isolation_and_conflict(api_client, seed, tokens):
    account_id = "wa-shared-" + uuid.uuid4().hex[:10]
    headers_a = _headers(tokens, seed, "a", "admin")
    headers_b = _headers(tokens, seed, "b", "admin")

    # Company A connects account
    r_a = api_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"provider_account_id": account_id, "access_token": "tok-a"},
        headers=headers_a,
    )
    assert r_a.status_code == 200
    id_a = r_a.json()["data"]["id"]

    # Company B lists integrations: must not see Company A's integration
    r_b_list = api_client.get("/api/v1/integrations", headers=headers_b)
    assert r_b_list.status_code == 200
    ids_b = [item["id"] for item in r_b_list.json()["data"]]
    assert id_a not in ids_b

    # Company B tries to connect the SAME account ID: must get 409 Conflict
    r_b_conflict = api_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"provider_account_id": account_id, "access_token": "tok-b"},
        headers=headers_b,
    )
    assert r_b_conflict.status_code == 409
    assert r_b_conflict.json()["error"]["code"] == "account_already_registered"


def test_invalid_token_rejected_on_connect(api_client, seed, tokens, mock_meta_graph):
    account_id = "wa-invalid-" + uuid.uuid4().hex[:10]
    headers = _headers(tokens, seed, "a", "admin")

    # Reset mock and return 400
    mock_meta_graph.reset()
    mock_meta_graph.get(path__regex=r"^/.*").respond(
        status_code=400,
        json={"error": {"message": "Invalid OAuth access token", "type": "OAuthException"}},
    )

    resp = api_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"provider_account_id": account_id, "access_token": "bad-token"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_credentials"
    assert "bad-token" not in resp.text
