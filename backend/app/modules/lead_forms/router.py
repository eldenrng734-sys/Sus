from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.types import Message

from app.database.session import get_session
from app.modules.lead_forms.schemas import PublicFormSubmission
from app.modules.lead_forms.service import submit_public_form

MAX_REQUEST_BODY_BYTES = 16 * 1024


class LimitedBodyRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_handler = super().get_route_handler()

        async def handler(request: Request) -> Response:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_REQUEST_BODY_BYTES:
                        raise HTTPException(status_code=413)
                except ValueError:
                    pass

            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_REQUEST_BODY_BYTES:
                    raise HTTPException(status_code=413)

            body_bytes = bytes(body)
            sent = False

            async def replay_body() -> Message:
                nonlocal sent
                if sent:
                    return {"type": "http.request", "body": b"", "more_body": False}
                sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            replay_request = Request(request.scope, receive=replay_body)
            return await original_handler(replay_request)

        return handler


router = APIRouter(
    prefix="/api/v1/public/forms",
    tags=["public forms"],
    route_class=LimitedBodyRoute,
)


@router.post("/{form_id}/submit", status_code=201)
def post_form_submission(
    form_id: str,
    submission: PublicFormSubmission,
    session: Session = Depends(get_session),
) -> dict[str, dict[str, str]]:
    return submit_public_form(session, public_id=form_id, submission=submission)
