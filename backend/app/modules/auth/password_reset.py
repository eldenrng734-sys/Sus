from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.database.session import get_session
from app.modules.auth import tokens
from app.modules.auth.emails import send_password_reset_email, send_verification_email
from app.modules.auth.errors import AuthError
from app.modules.auth.models import RefreshToken
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

def revoke_all_for_user(db: Session, user_id) -> None:
    """Log the user out everywhere by revoking all their refresh tokens."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )

RESET_REQUESTED = {"data": {"message": "If the account exists, a reset email has been sent."}}
VERIFY_REQUESTED = {
    "data": {"message": "If the account exists and is unverified, an email has been sent."}
}


class EmailBody(BaseModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().lower()


class TokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResetConfirmBody(TokenBody):
    new_password: str = Field(min_length=12, max_length=128)


def _invalid_token() -> AuthError:
    return AuthError(400, "invalid_or_expired_token", "This link is invalid or has expired")


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    body: EmailBody, background: BackgroundTasks, db: Session = Depends(get_session)
):
    user = db.scalar(select(User).where(User.email == body.email, User.is_active.is_(True)))
    if user is not None:
        raw = tokens.create_token(
            db,
            user.id,
            tokens.PASSWORD_RESET,
            timedelta(minutes=settings.password_reset_ttl_minutes),
        )
        db.commit()
        # Sent after the response, so it doesn't slow this request down.
        background.add_task(send_password_reset_email, user.email, raw)
    # Same answer whether or not the account exists (prevents email guessing).
    return RESET_REQUESTED


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(body: ResetConfirmBody, db: Session = Depends(get_session)):
    user_id = tokens.consume_token(db, body.token, tokens.PASSWORD_RESET)
    if user_id is None:
        raise _invalid_token()

    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=hash_password(body.new_password))
    )
    revoke_all_for_user(db, user_id)  # log the user out everywhere
    db.commit()  # token used + password changed + sessions revoked, all or nothing
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(body: TokenBody, db: Session = Depends(get_session)):
    user_id = tokens.consume_token(db, body.token, tokens.EMAIL_VERIFICATION)
    if user_id is None:
        raise _invalid_token()
    db.execute(
        update(User)
        .where(User.id == user_id, User.email_verified_at.is_(None))
        .values(email_verified_at=datetime.now(timezone.utc))
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    body: EmailBody, background: BackgroundTasks, db: Session = Depends(get_session)
):
    user = db.scalar(
        select(User).where(
            User.email == body.email,
            User.is_active.is_(True),
            User.email_verified_at.is_(None),
        )
    )
    if user is not None:
        raw = tokens.create_token(
            db,
            user.id,
            tokens.EMAIL_VERIFICATION,
            timedelta(hours=settings.email_verification_ttl_hours),
        )
        db.commit()
        background.add_task(send_verification_email, user.email, raw)
    return VERIFY_REQUESTED