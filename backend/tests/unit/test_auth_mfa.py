from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pyotp
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.modules.auth import mfa, service, sessions
from app.modules.auth.errors import AuthError
from app.modules.auth.schemas import LoginRequest


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "mfa_encryption_key", key)
    return key


def _user(*, mfa_enabled=False):
    return SimpleNamespace(
        id="b57c4718-8ff3-4719-b3f0-56a124948ccb",
        email="admin@example.com",
        full_name="Admin",
        password_hash="password-hash",
        email_verified_at=datetime.now(UTC),
        is_active=True,
        is_platform_admin=False,
        mfa_enabled=mfa_enabled,
        mfa_secret_encrypted=None,
        mfa_last_used_step=None,
        last_login_at=None,
    )


def test_mfa_secret_is_encrypted_and_round_trips(fernet_key):
    secret = pyotp.random_base32()

    encrypted = mfa.encrypt_secret(secret)

    assert secret.encode() not in encrypted
    assert mfa.decrypt_secret(encrypted) == secret


def test_mfa_secret_cannot_be_decrypted_with_another_key(fernet_key, monkeypatch):
    encrypted = mfa.encrypt_secret(pyotp.random_base32())
    monkeypatch.setattr(settings, "mfa_encryption_key", Fernet.generate_key().decode())

    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        mfa.decrypt_secret(encrypted)


def test_totp_code_is_accepted_once_only():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    code = totp.at(now)
    accepted_step = mfa._match_totp_step(secret, code, None)

    assert accepted_step is not None
    assert mfa._match_totp_step(secret, code, accepted_step) is None


def test_admin_password_login_returns_enrollment_challenge_without_session(monkeypatch, fernet_key):
    user = _user()
    db = MagicMock()
    db.scalar.return_value = user
    monkeypatch.setattr(service, "check_login_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "verify_password", lambda password, hashed: True)
    monkeypatch.setattr(service.mfa, "is_admin_user", lambda session, user: True)
    monkeypatch.setattr(service.mfa, "issue_challenge", lambda *args: "enrollment-challenge")
    monkeypatch.setattr(service, "record_login_attempt", lambda *args, **kwargs: None)
    start_session = MagicMock()
    monkeypatch.setattr(service.sessions, "start_session", start_session)

    data, refresh_token = service.login(
        db,
        LoginRequest(email="admin@example.com", password="correct-password"),
    )

    assert data["mfa_setup_required"] is True
    assert data["mfa_required"] is False
    assert data["challenge"] == "enrollment-challenge"
    assert refresh_token is None
    start_session.assert_not_called()
    db.commit.assert_called_once()


def test_mfa_enabled_user_password_login_returns_verification_challenge(monkeypatch):
    user = _user(mfa_enabled=True)
    db = MagicMock()
    db.scalar.return_value = user
    monkeypatch.setattr(service, "check_login_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "verify_password", lambda password, hashed: True)
    monkeypatch.setattr(service.mfa, "issue_challenge", lambda *args: "login-challenge")
    monkeypatch.setattr(service, "record_login_attempt", lambda *args, **kwargs: None)
    start_session = MagicMock()
    monkeypatch.setattr(service.sessions, "start_session", start_session)

    data, refresh_token = service.login(
        db,
        LoginRequest(email="admin@example.com", password="correct-password"),
    )

    assert data["mfa_required"] is True
    assert data["mfa_setup_required"] is False
    assert data["challenge"] == "login-challenge"
    assert refresh_token is None
    start_session.assert_not_called()


def test_admin_access_requires_totp_assurance(monkeypatch):
    user = _user(mfa_enabled=True)

    with pytest.raises(AuthError) as error:
        mfa.require_mfa_access(MagicMock(), user, ["pwd"])

    assert error.value.code == "mfa_required"
    mfa.require_mfa_access(MagicMock(), user, ["pwd", "totp"])


@pytest.mark.parametrize(
    ("mfa_verified", "expected_amr"),
    [(False, ["pwd"]), (True, ["pwd", "totp"])],
)
def test_started_refresh_session_preserves_mfa_assurance(monkeypatch, mfa_verified, expected_amr):
    db = MagicMock()
    monkeypatch.setattr(sessions, "create_access_token", lambda user_id, sid, amr: amr)
    monkeypatch.setattr(sessions, "generate_csrf_token", lambda: "csrf")

    session_data = sessions.start_session(
        db,
        "b57c4718-8ff3-4719-b3f0-56a124948ccb",
        None,
        None,
        mfa_verified=mfa_verified,
    )

    stored_token = db.add.call_args.args[0]
    assert stored_token.mfa_verified is mfa_verified
    assert session_data["access_token"] == expected_amr
