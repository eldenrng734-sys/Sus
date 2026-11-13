from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import AuthAttempt


class LoginRateLimitExceeded(Exception):
    """Raised when login failures exceed the configured limit."""


def count_recent_failures(
    session: Session,
    *,
    email: str,
    ip_address: str | None,
    window_minutes: int,
) -> tuple[int, int]:
    """Count recent failed attempts for an email and IP address."""

    since = datetime.now(UTC) - timedelta(minutes=window_minutes)

    email_count = (
        session.scalar(
            select(func.count(AuthAttempt.id)).where(
                AuthAttempt.email == email.strip().lower(),
                AuthAttempt.success.is_(False),
                AuthAttempt.created_at >= since,
            )
        )
        or 0
    )

    ip_count = 0

    if ip_address:
        ip_count = (
            session.scalar(
                select(func.count(AuthAttempt.id)).where(
                    AuthAttempt.ip_address == ip_address,
                    AuthAttempt.success.is_(False),
                    AuthAttempt.created_at >= since,
                )
            )
            or 0
        )

    return email_count, ip_count


def check_login_rate_limit(
    session: Session,
    *,
    email: str,
    ip_address: str | None,
    window_minutes: int,
    max_email_failures: int,
    max_ip_failures: int,
) -> None:
    """Raise an exception if either configured limit has been reached."""

    email_count, ip_count = count_recent_failures(
        session,
        email=email,
        ip_address=ip_address,
        window_minutes=window_minutes,
    )

    if email_count >= max_email_failures:
        raise LoginRateLimitExceeded("Too many login attempts. Try again later.")

    if ip_address and ip_count >= max_ip_failures:
        raise LoginRateLimitExceeded("Too many login attempts. Try again later.")


def record_login_attempt(
    session: Session,
    *,
    email: str,
    ip_address: str | None,
    success: bool,
) -> AuthAttempt:
    """Add an attempt to the current transaction. Caller owns commit/rollback."""

    attempt = AuthAttempt(
        email=email.strip().lower(),
        ip_address=ip_address,
        success=success,
    )
    session.add(attempt)
    return attempt
