import uuid

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 48)


def test_hash_is_argon2id_and_not_the_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed.startswith("$argon2id$")
    assert "correct-horse" not in hashed


def test_same_password_gives_different_hashes():
    assert hash_password("same-password-123") != hash_password("same-password-123")


def test_verify_password():
    hashed = hash_password("my-secret-pass-1")
    assert verify_password("my-secret-pass-1", hashed) is True
    assert verify_password("wrong-pass", hashed) is False
    assert verify_password("anything", "not-a-hash") is False


def test_token_roundtrip_has_no_role_or_tenant():
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    payload = decode_access_token(create_access_token(user_id, session_id))
    assert payload["sub"] == str(user_id)
    assert payload["sid"] == str(session_id)
    assert payload["type"] == "access"
    assert "role" not in payload
    assert "tenant_id" not in payload


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = create_access_token(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_key_is_rejected(monkeypatch):
    token = create_access_token(uuid.uuid4(), uuid.uuid4())
    monkeypatch.setattr(settings, "jwt_secret_key", "y" * 48)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_missing_secret_refuses_to_issue_tokens(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "")
    with pytest.raises(RuntimeError):
        create_access_token(uuid.uuid4(), uuid.uuid4())
