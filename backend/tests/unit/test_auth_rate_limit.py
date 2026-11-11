from unittest.mock import MagicMock

import pytest

from app.modules.auth.rate_limit import (
    LoginRateLimitExceeded,
    check_login_rate_limit,
    count_recent_failures,
    record_login_attempt,
)


def test_count_recent_failures():
    session = MagicMock()
    session.scalar.side_effect = [2, 3]

    email_count, ip_count = count_recent_failures(
        session,
        email="TEST@EXAMPLE.COM",
        ip_address="127.0.0.1",
        window_minutes=15,
    )

    assert email_count == 2
    assert ip_count == 3


def test_email_rate_limit_exceeded():
    session = MagicMock()
    session.scalar.side_effect = [5, 0]

    with pytest.raises(LoginRateLimitExceeded):
        check_login_rate_limit(
            session,
            email="test@example.com",
            ip_address="127.0.0.1",
            window_minutes=15,
            max_email_failures=5,
            max_ip_failures=20,
        )


def test_ip_rate_limit_exceeded():
    session = MagicMock()
    session.scalar.side_effect = [2, 20]

    with pytest.raises(LoginRateLimitExceeded):
        check_login_rate_limit(
            session,
            email="test@example.com",
            ip_address="127.0.0.1",
            window_minutes=15,
            max_email_failures=5,
            max_ip_failures=20,
        )


def test_record_login_attempt_normalizes_email():
    session = MagicMock()

    attempt = record_login_attempt(
        session,
        email=" TEST@EXAMPLE.COM ",
        ip_address="127.0.0.1",
        success=False,
    )

    assert attempt.email == "test@example.com"
    assert attempt.success is False
    session.add.assert_called_once_with(attempt)


def test_rate_limit_allows_attempts_below_limit():
    session = MagicMock()
    session.scalar.side_effect = [2, 3]

    check_login_rate_limit(
        session,
        email="test@example.com",
        ip_address="127.0.0.1",
        window_minutes=15,
        max_email_failures=5,
        max_ip_failures=20,
    )
