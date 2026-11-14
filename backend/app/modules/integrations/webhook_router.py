"""FastAPI routes for Meta and WhatsApp webhooks."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.integrations import webhooks

router = APIRouter(
    prefix="/api/v1/webhooks",
    tags=["webhooks"],
)


@router.get("/{provider}")
def verify_webhook(
    provider: str,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> PlainTextResponse:
    if provider not in webhooks.PROVIDERS:
        raise AuthError(404, "not_found", "Unknown provider")

    result = webhooks.verify_challenge(mode, token, challenge, provider=provider)
    return PlainTextResponse(result)


@router.post("/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_session),
) -> dict:
    if provider not in webhooks.PROVIDERS:
        raise AuthError(404, "not_found", "Unknown provider")

    declared = request.headers.get("content-length")

    if declared and declared.isdigit():
        if int(declared) > webhooks.MAX_BODY_BYTES:
            raise AuthError(
                413,
                "payload_too_large",
                "Webhook body is too large",
            )

    raw_body = await request.body()

    if len(raw_body) > webhooks.MAX_BODY_BYTES:
        raise AuthError(
            413,
            "payload_too_large",
            "Webhook body is too large",
        )

    result = await webhooks.receive(
        session,
        provider,
        raw_body,
        x_hub_signature_256,
    )

    return {
        "status": "ok",
        **result,
    }
