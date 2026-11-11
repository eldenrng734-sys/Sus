import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_session
from app.modules.auth import mfa, service, sessions
from app.modules.auth.errors import AuthError
from app.modules.auth.schemas import (
    LoginRequest,
    MfaChallengeRequest,
    MfaCodeRequest,
    SignupRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
REFRESH_PATH = "/api/v1/auth"
CsrfHeader = Annotated[str | None, Header(alias="X-CSRF-Token")]


def _client_info(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = (request.headers.get("user-agent") or "")[:300] or None
    return ip, ua


def _set_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    max_age = settings.refresh_token_expire_days * 24 * 3600
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=REFRESH_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


def _check_csrf_and_origin(request: Request, header_token: str | None) -> None:
    """Cookie-based endpoints need an allowed Origin and a matching CSRF header + cookie."""
    if request.headers.get("origin") not in settings.allowed_origins:
        raise AuthError(403, "forbidden", "Origin not allowed")
    cookie_token = request.cookies.get(CSRF_COOKIE) or ""
    if not header_token or not secrets.compare_digest(header_token.encode(), cookie_token.encode()):
        raise AuthError(403, "forbidden", "CSRF check failed")


@router.post("/signup", status_code=201)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> dict:
    return {"data": service.signup(session, body)}


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    ip, ua = _client_info(request)
    data, refresh_token = service.login(session, body, ip, ua)
    if refresh_token is not None:
        _set_cookies(response, refresh_token, data["csrf_token"])
    return {"data": data}


@router.post("/mfa/setup")
def start_mfa_enrollment(
    body: MfaChallengeRequest,
    session: Session = Depends(get_session),
) -> dict:
    return {"data": mfa.start_enrollment(session, body.challenge)}


@router.post("/mfa/confirm")
def confirm_mfa_enrollment(
    body: MfaCodeRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    ip, ua = _client_info(request)
    data, refresh_token = mfa.confirm_enrollment(
        session,
        body.challenge,
        body.code,
        ip,
        ua,
    )
    _set_cookies(response, refresh_token, data["csrf_token"])
    return {"data": data}


@router.post("/mfa/verify")
def verify_mfa(
    body: MfaCodeRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    ip, ua = _client_info(request)
    data, refresh_token = mfa.verify_login(
        session,
        body.challenge,
        body.code,
        ip,
        ua,
    )
    _set_cookies(response, refresh_token, data["csrf_token"])
    return {"data": data}


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    x_csrf_token: CsrfHeader = None,
    session: Session = Depends(get_session),
) -> dict:
    _check_csrf_and_origin(request, x_csrf_token)
    ip, ua = _client_info(request)
    data, new_refresh = sessions.refresh(session, request.cookies.get(REFRESH_COOKIE), ip, ua)
    _set_cookies(response, new_refresh, data["csrf_token"])
    return {"data": data}


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    x_csrf_token: CsrfHeader = None,
    session: Session = Depends(get_session),
) -> Response:
    _check_csrf_and_origin(request, x_csrf_token)
    sessions.logout(session, request.cookies.get(REFRESH_COOKIE))
    response = Response(status_code=204)
    _clear_cookies(response)
    return response
