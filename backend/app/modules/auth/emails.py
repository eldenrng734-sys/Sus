import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import settings


def _send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(msg)


def send_password_reset_email(to: str, raw_token: str) -> None:
    link = f"{settings.frontend_base_url}/reset-password?token={quote(raw_token)}"
    _send(
        to,
        "Reset your password",
        (
            "We received a request to reset your password.\n\n"
            f"Open this link within {settings.password_reset_ttl_minutes} minutes:\n{link}\n\n"
            "If you didn't ask for this, you can ignore this email."
        ),
    )


def send_verification_email(to: str, raw_token: str) -> None:
    link = f"{settings.frontend_base_url}/verify-email?token={quote(raw_token)}"
    _send(
        to,
        "Verify your email address",
        (
            "Please confirm your email address.\n\n"
            f"Open this link within {settings.email_verification_ttl_hours} hours:\n{link}\n\n"
            "If you didn't create an account, you can ignore this email."
        ),
    )
