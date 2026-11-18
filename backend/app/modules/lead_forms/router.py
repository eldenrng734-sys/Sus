import secrets
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.types import Message

from app.core.tenancy import TenantContext, get_tenant_context
from app.database.session import get_session
from app.modules.lead_forms.models import LeadForm
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


tenant_router = APIRouter(
    prefix="/api/v1/lead-forms",
    tags=["lead forms"],
)


@tenant_router.get("/primary", response_model=dict)
def get_primary_lead_form(
    context: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_session),
) -> dict:
    """Get or auto-create the active public lead form and embed snippet for this company."""
    form = session.scalar(
        select(LeadForm).where(
            LeadForm.tenant_id == context.tenant_id,
            LeadForm.is_active.is_(True),
        )
    )
    if form is None:
        public_id = f"lf_{secrets.token_hex(8)}"
        form = LeadForm(
            tenant_id=context.tenant_id,
            public_id=public_id,
            name="Website Contact Form",
            allowed_fields=["name", "email", "phone", "notes"],
            consent_text="I agree to receive communications regarding my inquiry.",
            is_active=True,
        )
        session.add(form)
        session.commit()

    embed_html = (
        f'<!-- AI Sales CRM Lead Form Embed -->\n'
        f'<form action="/api/v1/public/forms/{form.public_id}/submit" method="POST" class="crm-lead-form">\n'
        f'  <div class="form-group">\n'
        f'    <label for="lead-name">Full Name *</label>\n'
        f'    <input type="text" id="lead-name" name="name" required placeholder="Jane Doe" />\n'
        f'  </div>\n'
        f'  <div class="form-group">\n'
        f'    <label for="lead-email">Email Address *</label>\n'
        f'    <input type="email" id="lead-email" name="email" required placeholder="jane@example.com" />\n'
        f'  </div>\n'
        f'  <div class="form-group">\n'
        f'    <label for="lead-phone">Phone Number *</label>\n'
        f'    <input type="tel" id="lead-phone" name="phone" required placeholder="+8801700000000" />\n'
        f'  </div>\n'
        f'  <div class="form-group">\n'
        f'    <label for="lead-notes">Message / Inquiry</label>\n'
        f'    <textarea id="lead-notes" name="notes" placeholder="How can we assist you?"></textarea>\n'
        f'  </div>\n'
        f'  <!-- Honeypot anti-spam field (hidden) -->\n'
        f'  <input type="text" name="company_website" style="display:none !important;" tabindex="-1" autocomplete="off" />\n'
        f'  <button type="submit">Submit Inquiry</button>\n'
        f'</form>'
    )
    return {
        "data": {
            "id": str(form.id),
            "public_id": form.public_id,
            "name": form.name,
            "allowed_fields": form.allowed_fields or ["name", "email", "phone", "notes"],
            "consent_text": form.consent_text,
            "is_active": form.is_active,
            "embed_code": embed_html,
            "endpoint_url": f"/api/v1/public/forms/{form.public_id}/submit",
        }
    }
