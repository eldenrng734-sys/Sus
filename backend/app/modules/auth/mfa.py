import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_refresh_token
from app.modules.audit.models import AuditLog
from app.modules.auth import sessions
from app.modules.auth.errors import AuthError
from app.modules.auth.models import MfaLoginChallenge, MfaRecoveryCode, RefreshToken
from app.modules.auth.rate_limit import (
    LoginRateLimitExceeded,
    check_login_rate_limit,
    record_login_attempt,
)
from app.modules.tenants.models import TenantMembership
from app.modules.users.models import User

CHALLENGE_TTL = timedelta(minutes=5)
RECOVERY_CODE_COUNT = 10


def _invalid_challenge() -> AuthError:
    return AuthError(401, "invalid_mfa_challenge", "MFA challenge is invalid or expired")


def _invalid_code() -> AuthError:
    return AuthError(401, "invalid_mfa_code", "Invalid MFA code")


def _fernet() -> Fernet:
    if not settings.mfa_encryption_key:
        raise RuntimeError("MFA_ENCRYPTION_KEY is required to use MFA")
    try:
        return Fernet(settings.mfa_encryption_key.encode())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("MFA_ENCRYPTION_KEY must be a valid Fernet key") from exc


def validate_encryption_key() -> None:
    _fernet()


def encrypt_secret(secret: str) -> bytes:
    return _fernet().encrypt(secret.encode())


def decrypt_secret(encrypted_secret: bytes) -> str:
    try:
        return _fernet().decrypt(encrypted_secret).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Stored MFA secret cannot be decrypted") from exc


def is_admin_user(session: Session, user: User) -> bool:
    if user.is_platform_admin:
        return True

    session.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": str(user.id)},
    )
    return (
        session.scalar(
            select(TenantMembership.id)
            .where(
                TenantMembership.user_id == user.id,
                TenantMembership.is_active.is_(True),
                TenantMembership.role == "admin",
            )
            .limit(1)
        )
        is not None
    )


def issue_challenge(session: Session, user_id: uuid.UUID, purpose: str) -> str:
    now = datetime.now(UTC)
    session.execute(
        delete(MfaLoginChallenge).where(
            (MfaLoginChallenge.used_at.is_not(None))
            | (MfaLoginChallenge.expires_at <= now)
        )
    )
    raw_token = secrets.token_urlsafe(32)
    session.add(
        MfaLoginChallenge(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            purpose=purpose,
            expires_at=now + CHALLENGE_TTL,
        )
    )
    session.flush()
    return raw_token


def _load_challenge(
    session: Session, raw_token: str, purpose: str
) -> tuple[MfaLoginChallenge, User]:
    challenge = session.scalar(
        select(MfaLoginChallenge)
        .where(MfaLoginChallenge.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.purpose != purpose
        or challenge.used_at is not None
        or challenge.expires_at <= now
    ):
        raise _invalid_challenge()

    user = session.scalar(
        select(User).where(User.id == challenge.user_id).with_for_update()
    )
    if user is None or not user.is_active:
        raise _invalid_challenge()
    return challenge, user


def _check_mfa_rate_limit(session: Session, user: User, ip: str | None) -> None:
    try:
        check_login_rate_limit(
            session,
            email=user.email,
            ip_address=ip,
            window_minutes=15,
            max_email_failures=5,
            max_ip_failures=20,
        )
    except LoginRateLimitExceeded as exc:
        raise AuthError(
            429,
            "login_rate_limited",
            "Too many login attempts. Try again later.",
        ) from exc


def _record_mfa_failure(session: Session, user: User, ip: str | None) -> None:
    record_login_attempt(session, email=user.email, ip_address=ip, success=False)
    session.commit()


def _match_totp_step(secret: str, code: str, last_used_step: int | None) -> int | None:
    totp = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    current_step = totp.timecode(now)
    for step in (current_step - 1, current_step, current_step + 1):
        if step <= (last_used_step if last_used_step is not None else -1):
            continue
        step_time = datetime.fromtimestamp(step * totp.interval, UTC)
        if totp.verify(code, for_time=step_time):
            return step
    return None


def _recovery_code_row(session: Session, user_id: uuid.UUID, code: str) -> MfaRecoveryCode | None:
    digest = hashlib.sha256(code.encode()).hexdigest()
    rows = session.scalars(
        select(MfaRecoveryCode)
        .where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    )
    for row in rows:
        if hmac.compare_digest(row.code_hash, digest):
            return row
    return None


def _audit_mfa(session: Session, user: User, action: str, ip: str | None, ua: str | None) -> None:
    tenant_id = None
    if not user.is_platform_admin:
        session.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(user.id)},
        )
        tenant_id = session.scalar(
            select(TenantMembership.tenant_id)
            .where(
                TenantMembership.user_id == user.id,
                TenantMembership.role == "admin",
                TenantMembership.is_active.is_(True),
            )
            .limit(1)
        )
        if tenant_id is not None:
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )

    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=user.id,
            actor_type="platform_admin" if user.is_platform_admin else "user",
            action=action,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip,
            user_agent=ua,
            details={},
        )
    )


def _session_data(user: User, started: dict[str, str]) -> dict:
    return {
        "access_token": started["access_token"],
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "csrf_token": started["csrf_token"],
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "email_verified": user.email_verified_at is not None,
        },
    }


def start_enrollment(session: Session, challenge_token: str) -> dict[str, str]:
    _, user = _load_challenge(session, challenge_token, "enrollment")
    if not is_admin_user(session, user) or user.mfa_enabled:
        raise AuthError(403, "forbidden", "MFA enrollment is not available")

    secret = pyotp.random_base32()
    user.mfa_secret_encrypted = encrypt_secret(secret)
    session.commit()
    return {
        "secret": secret,
        "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=settings.mfa_issuer,
        ),
    }


def confirm_enrollment(
    session: Session,
    challenge_token: str,
    code: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[dict, str]:
    challenge, user = _load_challenge(session, challenge_token, "enrollment")
    if not is_admin_user(session, user) or user.mfa_enabled:
        raise AuthError(403, "forbidden", "MFA enrollment is not available")
    if user.mfa_secret_encrypted is None:
        raise AuthError(409, "mfa_setup_required", "Start MFA enrollment before confirming it")

    _check_mfa_rate_limit(session, user, ip)
    step = _match_totp_step(decrypt_secret(user.mfa_secret_encrypted), code, None)
    if step is None:
        _record_mfa_failure(session, user, ip)
        raise _invalid_code()

    now = datetime.now(UTC)
    user.mfa_enabled = True
    user.mfa_last_used_step = step
    user.last_login_at = now
    challenge.used_at = now
    recovery_codes = [secrets.token_urlsafe(12) for _ in range(RECOVERY_CODE_COUNT)]
    session.add_all(
        [
            MfaRecoveryCode(
                user_id=user.id,
                code_hash=hashlib.sha256(code.encode()).hexdigest(),
            )
            for code in recovery_codes
        ]
    )
    sessions.revoke_all_for_user(session, user.id)
    started = sessions.start_session(session, user.id, ip, user_agent, mfa_verified=True)
    record_login_attempt(session, email=user.email, ip_address=ip, success=True)
    _audit_mfa(session, user, "auth.mfa.enabled", ip, user_agent)
    session.commit()

    data = _session_data(user, started)
    data["recovery_codes"] = recovery_codes
    return data, started["refresh_token"]


def verify_login(
    session: Session,
    challenge_token: str,
    code: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[dict, str]:
    challenge, user = _load_challenge(session, challenge_token, "login")
    if not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise _invalid_challenge()

    _check_mfa_rate_limit(session, user, ip)
    totp_step = _match_totp_step(
        decrypt_secret(user.mfa_secret_encrypted),
        code,
        user.mfa_last_used_step,
    )
    recovery_row = None
    if totp_step is None:
        recovery_row = _recovery_code_row(session, user.id, code)
    if totp_step is None and recovery_row is None:
        _record_mfa_failure(session, user, ip)
        raise _invalid_code()

    now = datetime.now(UTC)
    challenge.used_at = now
    if totp_step is not None:
        user.mfa_last_used_step = totp_step
    else:
        assert recovery_row is not None
        recovery_row.used_at = now
    user.last_login_at = now
    started = sessions.start_session(session, user.id, ip, user_agent, mfa_verified=True)
    record_login_attempt(session, email=user.email, ip_address=ip, success=True)
    _audit_mfa(session, user, "auth.mfa.login", ip, user_agent)
    session.commit()
    return _session_data(user, started), started["refresh_token"]


def require_mfa_access(session: Session, user: User, amr: list[str]) -> None:
    if (user.mfa_enabled or is_admin_user(session, user)) and "totp" not in amr:
        raise AuthError(403, "mfa_required", "Complete MFA before accessing this resource")


def is_live_session(session: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(RefreshToken.id)
            .where(
                RefreshToken.family_id == session_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .limit(1)
        )
        is not None
    )
