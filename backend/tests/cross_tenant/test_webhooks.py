import hashlib
import hmac
import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.integrations.webhook_router import router
from tests.cross_tenant.support import set_tenant

SECRET = "whatsapp-test-secret"
URL = "/api/v1/webhooks/whatsapp"


@pytest.fixture(scope="module", autouse=True)
def _secrets():
    from pydantic import SecretStr

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "meta_app_secret", SecretStr(SECRET))
        patch.setattr(settings, "webhook_verify_token", SecretStr("verify-me"))
        yield


@pytest.fixture(scope="module")
def hook_client(admin_engine):
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)
    mini.include_router(router)

    def _session():
        with Session(admin_engine) as session:
            yield session

    mini.dependency_overrides[get_session] = _session
    return TestClient(mini)


@pytest.fixture(scope="module")
def account(admin_engine, seed):
    account_id = "pn-" + uuid.uuid4().hex[:10]
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        conn.execute(
            text(
                "INSERT INTO integrations (tenant_id, provider, provider_account_id) "
                "VALUES (:t, 'whatsapp', :a)"
            ),
            {"t": seed.a.id, "a": account_id},
        )
    return account_id


def _body(account_id: str, message_id: str) -> bytes:
    message = {"id": message_id, "from": "8801700000000", "type": "text", "text": {"body": "hi"}}
    value = {"metadata": {"phone_number_id": account_id}, "messages": [message]}
    payload = {"entry": [{"id": "waba", "changes": [{"field": "messages", "value": value}]}]}
    return json.dumps(payload).encode()


def _sig(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(client, body: bytes, signature: str | None):
    headers = {"Content-Type": "application/json"}
    if signature:
        headers["X-Hub-Signature-256"] = signature
    return client.post(URL, content=body, headers=headers)


def _count(admin_engine, seed, event_id: str) -> int:
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        return conn.scalar(
            text("SELECT count(*) FROM webhook_events WHERE event_id = :e"), {"e": event_id}
        )


def test_valid_webhook_is_stored_once_even_if_sent_twice(hook_client, admin_engine, seed, account):
    mid = "wamid." + uuid.uuid4().hex
    body = _body(account, mid)
    assert _post(hook_client, body, _sig(body)).status_code == 200
    assert _post(hook_client, body, _sig(body)).status_code == 200
    assert _count(admin_engine, seed, mid) == 1


def test_bad_signature_is_rejected_and_not_stored(hook_client, admin_engine, seed, account):
    mid = "wamid." + uuid.uuid4().hex
    body = _body(account, mid)
    r = _post(hook_client, body, _sig(body, "wrong-secret"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_signature"
    assert _count(admin_engine, seed, mid) == 0


def test_missing_signature_is_rejected(hook_client, account):
    assert _post(hook_client, _body(account, "wamid.x"), None).status_code == 401


def test_unknown_account_returns_200_and_stores_nothing(hook_client, admin_engine, seed):
    mid = "wamid." + uuid.uuid4().hex
    body = _body("pn-does-not-exist", mid)
    res = _post(hook_client, body, _sig(body))
    assert res.status_code == 200
    assert _count(admin_engine, seed, mid) == 0


def test_malformed_json_with_valid_signature_is_400(hook_client):
    body = b"{not json"
    assert _post(hook_client, body, _sig(body)).status_code == 400


def test_oversized_body_is_413(hook_client):
    body = b"x" * 1_000_001
    assert _post(hook_client, body, _sig(body)).status_code == 413


def test_verification_challenge(hook_client):
    good = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"}
    ok = hook_client.get(URL, params=good)
    assert ok.status_code == 200 and ok.text == "42"
    bad = hook_client.get(URL, params={**good, "hub.verify_token": "nope"})
    assert bad.status_code == 403
