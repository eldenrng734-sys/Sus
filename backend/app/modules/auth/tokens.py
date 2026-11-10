import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.auth.models import AuthToken

PASSWORD_RESET = "password_reset"
EMAIL_VERIFICATION = "email_verification"


def hash_token(raw: str) -> str:
    # SHA-256 is fine here: the token is long and random, so it can't be brute-forced
    # (unlike a password, which needs Argon2).
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_token(db: Session, user_id: uuid.UUID, purpose: str, ttl: timedelta) -> str:
    """Create a token and return the RAW value. Email it; never store or log it.

    Older unused tokens of the same purpose for this user are invalidated,
    so only the newest link works.
    """
    now = datetime.now(timezone.utc)
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=now + ttl,
        )
    )
    db.flush()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> uuid.UUID | None:
    """Mark a valid token as used and return its user_id, or None if invalid.

    A single UPDATE ... RETURNING does the check and the marking at once, so two
    simultaneous requests can never both use the same token.
    """
    now = datetime.now(timezone.utc)
    row = db.execute(
        update(AuthToken)
        .where(
            AuthToken.token_hash == hash_token(raw),
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(AuthToken.user_id)
    ).first()
    return row[0] if row else None
