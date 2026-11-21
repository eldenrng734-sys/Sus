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
REFRESH_PATH = "/"
CsrfHeader = Annotated[str | None, Header(alias="X-CSRF-Token")]


def _client_info(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = (request.headers.get("user-agent") or "")[:300] or None
    return ip, ua


def _set_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    # Expire any legacy scoped cookies so they do not shadow path="/" cookies
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    response.delete_cookie(CSRF_COOKIE, path="/api/v1/auth")

    max_age = settings.refresh_token_expire_days * 24 * 3600
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/api/v1/auth")


def _is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    allowed = (
        set(settings.allowed_origins)
        | {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        }
        | ({settings.frontend_base_url.rstrip("/")} if settings.frontend_base_url else set())
    )
    if origin in allowed:
        return True

    # In development/test environments, allow developer tunnels (Cloudflare, ngrok, localtunnel)
    if settings.app_env != "production":
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        host = parsed.hostname or ""
        if (
            host.endswith(".trycloudflare.com")
            or host.endswith(".ngrok-free.app")
            or host.endswith(".loca.lt")
            or host in {"localhost", "127.0.0.1"}
        ):
            return True

    return False


def _check_csrf_and_origin(request: Request, header_token: str | None) -> None:
    """Cookie-based endpoints need an allowed Origin and a matching CSRF header + cookie."""
    import logging as _log

    _logger = _log.getLogger("app.auth")
    origin = request.headers.get("origin")
    if not _is_origin_allowed(origin):
        _logger.warning("auth_origin_rejected: origin=%r not in allowed", origin)
        raise AuthError(403, "forbidden", f"Origin '{origin}' not allowed")

    # Read cookie tokens from both parsed request.cookies and raw Cookie header
    # to handle cases where multiple cookies exist across paths.
    cookie_str = request.headers.get("cookie", "")
    cookie_tokens: list[str] = []
    for part in cookie_str.split(";"):
        k, _, v = part.strip().partition("=")
        if k == CSRF_COOKIE and v:
            cookie_tokens.append(v)
    parsed_cookie = request.cookies.get(CSRF_COOKIE)
    if parsed_cookie and parsed_cookie not in cookie_tokens:
        cookie_tokens.append(parsed_cookie)

    matches = bool(
        header_token
        and any(
            secrets.compare_digest(header_token.encode(), ct.encode())
            for ct in cookie_tokens
        )
    )
    if not matches:
        _logger.warning(
            "auth_csrf_rejected: header_token=%r cookie_tokens=%r",
            header_token,
            cookie_tokens,
        )
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
