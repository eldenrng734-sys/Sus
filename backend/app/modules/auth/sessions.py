import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.modules.auth.errors import AuthError
from app.modules.auth.models import RefreshToken
from app.modules.users.models import User


def _now() -> datetime:
    return datetime.now(UTC)


def _new_token(
    db: Session, user_id: uuid.UUID, family_id: uuid.UUID, ip: str | None, ua: str | None
) -> tuple[RefreshToken, str]:
    raw = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        family_id=family_id,
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
        ip_address=ip,
        user_agent=ua,
    )
    db.add(row)
    db.flush()
    return row, raw


def start_session(
    db: Session, user_id: uuid.UUID, ip: str | None, ua: str | None
) -> dict[str, str]:
    """Called at login. The caller commits. sid in the access token = family_id."""
    family_id = uuid.uuid4()
    _, raw = _new_token(db, user_id, family_id, ip, ua)
    return {
        "refresh_token": raw,
        "csrf_token": generate_csrf_token(),
        "access_token": create_access_token(user_id, family_id),
    }


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    """Call this on password reset, deactivation, role removal and MFA reset."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def refresh(db: Session, raw_token: str | None, ip: str | None, ua: str | None) -> tuple[dict, str]:
    if not raw_token:
        raise AuthError(401, "unauthorized", "Missing refresh token")

    # FOR UPDATE: two requests with the same token cannot both succeed.
    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if row is None:
        raise AuthError(401, "unauthorized", "Invalid refresh token")

    if row.revoked_at is not None:
        # An old token came back: it was copied. Cancel the whole family.
        revoke_family(db, row.family_id)
        db.commit()
        raise AuthError(401, "session_revoked", "Session revoked. Please log in again")

    if row.expires_at <= _now():
        raise AuthError(401, "unauthorized", "Refresh token expired")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        revoke_family(db, row.family_id)
        db.commit()
        raise AuthError(401, "unauthorized", "Session is no longer valid")

    new_row, new_raw = _new_token(db, row.user_id, row.family_id, ip, ua)
    new_row.tenant_id = row.tenant_id
    row.revoked_at = _now()
    row.replaced_by_id = new_row.id
    row.last_used_at = _now()
    access = create_access_token(row.user_id, row.family_id)
    db.commit()

    data = {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "csrf_token": generate_csrf_token(),
    }
    return data, new_raw


def logout(db: Session | None, raw_token: str | None) -> None:
    """Always safe to repeat. Nothing to revoke is not an error."""
    if not raw_token or db is None:
        return
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if row is not None:
        revoke_family(db, row.family_id)
        db.commit()
