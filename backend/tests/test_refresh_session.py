import pytest
from fastapi.testclient import TestClient

from app.core.security import generate_refresh_token, hash_refresh_token
from app.database.session import get_session
from app.main import app

ORIGIN = "http://localhost:8000"


def _fake_session():
    yield None


@pytest.fixture
def client():
    app.dependency_overrides[get_session] = _fake_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_refresh_token_is_random_and_hashed():
    a, b = generate_refresh_token(), generate_refresh_token()
    assert a != b and len(a) >= 48
    assert hash_refresh_token(a) == hash_refresh_token(a)
    assert hash_refresh_token(a) != a
    assert len(hash_refresh_token(a)) == 64


def test_refresh_without_csrf_is_rejected(client):
    r = client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_refresh_with_bad_origin_is_rejected(client):
    r = client.post(
        "/api/v1/auth/refresh",
        headers={
            "Origin": "https://evil.example",
            "X-CSRF-Token": "abc",
            "Cookie": "csrf_token=abc",
        },
    )
    assert r.status_code == 403


def test_refresh_with_mismatched_csrf_is_rejected(client):
    r = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": ORIGIN, "X-CSRF-Token": "abc", "Cookie": "csrf_token=xyz"},
    )
    assert r.status_code == 403


def test_refresh_without_cookie_is_unauthorized(client):
    r = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": ORIGIN, "X-CSRF-Token": "abc", "Cookie": "csrf_token=abc"},
    )
    assert r.status_code == 401


def test_logout_is_safe_to_repeat_and_clears_cookies(client):
    headers = {"Origin": ORIGIN, "X-CSRF-Token": "abc", "Cookie": "csrf_token=abc"}
    r = client.post("/api/v1/auth/logout", headers=headers)
    assert r.status_code == 204
    cookies = " ".join(r.headers.get_list("set-cookie"))
    assert "refresh_token" in cookies and "csrf_token" in cookies
