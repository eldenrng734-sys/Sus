import uuid
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


@pytest.fixture(autouse=True)
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


def test_invalid_mfa_login_code_is_rejected_and_recorded(monkeypatch):
    user = _user(mfa_enabled=True)
    user.mfa_secret_encrypted = mfa.encrypt_secret(pyotp.random_base32())
    challenge = SimpleNamespace(used_at=None)
    session = MagicMock()
    record_failure = MagicMock()
    monkeypatch.setattr(mfa, "_load_challenge", lambda *args: (challenge, user))
    monkeypatch.setattr(mfa, "_check_mfa_rate_limit", lambda *args: None)
    monkeypatch.setattr(mfa, "_match_totp_step", lambda *args: None)
    monkeypatch.setattr(mfa, "_recovery_code_row", lambda *args: None)
    monkeypatch.setattr(mfa, "_record_mfa_failure", record_failure)

    with pytest.raises(AuthError) as error:
        mfa.verify_login(session, "challenge", "000000", None, None)

    assert error.value.code == "invalid_mfa_code"
    record_failure.assert_called_once_with(session, user, None)


def test_recovery_code_is_consumed_on_successful_mfa_login(monkeypatch):
    user = _user(mfa_enabled=True)
    user.mfa_secret_encrypted = mfa.encrypt_secret(pyotp.random_base32())
    challenge = SimpleNamespace(used_at=None)
    recovery_row = SimpleNamespace(used_at=None)
    session = MagicMock()
    monkeypatch.setattr(mfa, "_load_challenge", lambda *args: (challenge, user))
    monkeypatch.setattr(mfa, "_check_mfa_rate_limit", lambda *args: None)
    monkeypatch.setattr(mfa, "_match_totp_step", lambda *args: None)
    monkeypatch.setattr(mfa, "_recovery_code_row", lambda *args: recovery_row)
    monkeypatch.setattr(mfa.sessions, "list_user_memberships", lambda *args: [])
    monkeypatch.setattr(
        mfa.sessions,
        "start_session",
        lambda *args, **kwargs: {
            "access_token": "access",
            "csrf_token": "csrf",
            "refresh_token": "refresh",
        },
    )
    monkeypatch.setattr(mfa, "record_login_attempt", lambda *args, **kwargs: None)
    monkeypatch.setattr(mfa, "_audit_mfa", lambda *args: None)

    data, refresh_token = mfa.verify_login(session, "challenge", "recovery-code", None, None)

    assert challenge.used_at is not None
    assert recovery_row.used_at is not None
    assert data["access_token"] == "access"
    assert refresh_token == "refresh"
    session.commit.assert_called_once()


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


def test_list_user_memberships_serializes_active_tenant_context():
    db = MagicMock()
    user_id = uuid.UUID("b57c4718-8ff3-4719-b3f0-56a124948ccb")
    tenant_id = uuid.UUID("63e1527e-eafa-4bd0-9e97-e98033e5f7c1")
    membership = SimpleNamespace(
        tenant_id=tenant_id,
        role="admin",
        team_id=None,
        is_active=True,
    )
    tenant = SimpleNamespace(name="Acme Traders")
    db.execute.return_value.all.return_value = [(membership, tenant)]

    result = sessions.list_user_memberships(db, user_id)

    assert result == [
        {
            "tenant_id": str(tenant_id),
            "tenant_name": "Acme Traders",
            "role": "admin",
            "team_id": None,
            "is_active": True,
        }
    ]
