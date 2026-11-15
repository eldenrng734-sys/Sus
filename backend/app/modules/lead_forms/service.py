import secrets
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database.session import set_tenant_context
from app.modules.lead_forms.models import LeadForm
from app.modules.lead_forms.schemas import PublicFormSubmission
from app.modules.leads.capture import CaptureError, CaptureInput, capture_lead


def submit_public_form(
    session: Session,
    *,
    public_id: str,
    submission: PublicFormSubmission,
) -> dict[str, dict[str, str]]:
    session.execute(
        text("SELECT set_config('app.public_form_id', :public_id, true)"),
        {"public_id": public_id},
    )
    try:
        form = session.scalar(
            select(LeadForm).where(
                LeadForm.public_id == public_id,
                LeadForm.is_active.is_(True),
            )
        )
    finally:
        session.execute(text("SELECT set_config('app.public_form_id', '', true)"))

    if form is None:
        raise HTTPException(status_code=404)

    set_tenant_context(session, str(form.tenant_id))

    if submission.honeypot:
        return {"data": {"status": "received"}}

    allowed = set(form.allowed_fields or [])
    utm = (
        submission.utm.model_dump(exclude_none=True)
        if submission.utm is not None and "utm" in allowed
        else {}
    )
    campaign = utm.get("campaign")
    reference = _new_reference()
    metadata = {
        "form_public_id": form.public_id,
        "consent_text": form.consent_text,
        "consent_version": submission.consent_version,
        "consent_given_at": datetime.now(UTC).isoformat(),
        "utm": utm,
        "submission_reference": reference,
    }

    try:
        result = capture_lead(
            session,
            tenant_id=form.tenant_id,
            data=CaptureInput(
                name=submission.name if "name" in allowed else "",
                email=submission.email if "email" in allowed else None,
                phone=submission.phone if "phone" in allowed else None,
                company_name=(submission.company_name if "company_name" in allowed else None),
                source="website_form",
                source_campaign=campaign[:200] if campaign else None,
                consent=True,
                consent_source="web_form",
                notes=submission.message if "message" in allowed else None,
                interaction_metadata=metadata,
            ),
        )
    except CaptureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.commit()
    return {"data": {"id": str(result.lead.id)}}


def _new_reference() -> str:
    return f"pf_{secrets.token_hex(4)}"
