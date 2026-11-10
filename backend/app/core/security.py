import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

# PasswordHasher uses Argon2id by default.
_hasher = PasswordHasher()

# Used at login when the email does not exist, so the response takes the same
# time either way (stops attackers from discovering which emails exist).
DUMMY_PASSWORD_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    """Turn a password into an Argon2id hash. The real password is never stored."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True only if the password matches the stored hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _require_secret() -> str:
    if len(settings.jwt_secret_key) < 32:
        raise RuntimeError("JWT_SECRET_KEY is missing or too short (need 32+ characters)")
    return settings.jwt_secret_key


def create_access_token(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    amr: list[str] | None = None,
) -> str:
    """Short-lived access token. It carries NO role and NO tenant (see API_CONTRACT 3.1)."""
    secret = _require_secret()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "type": "access",
        "amr": amr or ["pwd"],
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Check signature, expiry and type. Raises a jwt error if anything is wrong."""
    secret = _require_secret()
    payload = jwt.decode(
        token,
        secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub", "sid", "jti"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def generate_refresh_token() -> str:
    """A long random value. Only its hash is stored in the database."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
