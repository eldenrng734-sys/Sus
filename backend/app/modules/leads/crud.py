import base64
import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.leads.models import Interaction, Lead
from app.modules.leads.schemas import LeadCreate, LeadUpdate, NoteCreate
from app.modules.leads.transitions import check_transition

SORT_LIMIT_MAX = 100


def lead_out(lead: Lead) -> dict:
    return {
        "id": str(lead.id),
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "company_name": lead.company_name,
        "source": lead.source,
        "status": lead.status,
        "lost_reason": lead.lost_reason,
        "assigned_user_id": str(lead.assigned_user_id) if lead.assigned_user_id else None,
        "team_id": str(lead.team_id) if lead.team_id else None,
        "intent": lead.intent,
        "lead_score": lead.lead_score,
        "priority": lead.priority,
        "consent": lead.consent,
        "opted_out": lead.opted_out,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
    }


def _encode_cursor(lead: Lead) -> str:
    raw = f"{lead.created_at.isoformat()}|{lead.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, _, ident = raw.partition("|")
        return datetime.fromisoformat(stamp), uuid.UUID(ident)
    except Exception as exc:
        raise AuthError(400, "bad_request", "Invalid cursor") from exc


def _get_scoped(session: Session, ctx: TenantContext, lead_id: uuid.UUID) -> Lead:
    """404 (not 403) when the lead is outside the caller's scope or company."""
    lead = session.scalar(apply_data_scope(select(Lead).where(Lead.id == lead_id), Lead, ctx))
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")
    return lead


def create_lead(session: Session, ctx: TenantContext, body: LeadCreate) -> dict:
    clauses = []
    if body.email:
        clauses.append(Lead.email == body.email)
    if body.phone:
        clauses.append(Lead.phone == body.phone)
    exists = session.scalar(
        select(Lead.id).where(Lead.tenant_id == ctx.tenant_id, or_(*clauses)).limit(1)
    )
    if exists:
        raise AuthError(409, "duplicate_lead", "A lead with this email or phone already exists")

    lead = Lead(
        tenant_id=ctx.tenant_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        company_name=body.company_name,
        source="manual",
        priority="medium",
        consent=body.consent,
    )
    if ctx.role == "rep":
        lead.assigned_user_id = ctx.user_id
        lead.team_id = ctx.team_id
    elif ctx.role == "manager":
        lead.team_id = ctx.team_id
    session.add(lead)
    session.flush()

    session.add(
        Interaction(
            tenant_id=ctx.tenant_id,
            lead_id=lead.id,
            type="lead_created",
            source="manual",
            details={"actor_user_id": str(ctx.user_id)},
        )
    )
    if body.notes:
        session.add(
            Interaction(
                tenant_id=ctx.tenant_id,
                lead_id=lead.id,
                type="note",
                source="manual",
                details={"text": body.notes, "actor_user_id": str(ctx.user_id)},
            )
        )
    record_audit_event(
        session,
        action="lead.created",
        actor_type="user",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        entity_type="lead",
        entity_id=lead.id,
        details={},
    )
    session.commit()
    session.refresh(lead)
    return lead_out(lead)


def list_leads(
    session: Session,
    ctx: TenantContext,
    q: str | None,
    status: str | None,
    priority: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict], dict]:
    limit = max(1, min(limit, SORT_LIMIT_MAX))
    stmt = apply_data_scope(select(Lead), Lead, ctx)

    if q:
        if len(q) > 100:
            raise AuthError(422, "validation_error", "Search text is too long (max 100)")
        safe = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{safe}%"
        stmt = stmt.where(
            or_(
                Lead.name.ilike(like, escape="\\"),
                Lead.email.ilike(like, escape="\\"),
                Lead.phone.ilike(like, escape="\\"),
                Lead.company_name.ilike(like, escape="\\"),
            )
        )
    if status:
        stmt = stmt.where(Lead.status.in_([s for s in status.split(",") if s]))
    if priority:
        stmt = stmt.where(Lead.priority.in_([p for p in priority.split(",") if p]))
    if cursor:
        stamp, ident = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(Lead.created_at < stamp, and_(Lead.created_at == stamp, Lead.id < ident))
        )

    rows = session.scalars(
        stmt.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    meta = {"next_cursor": _encode_cursor(rows[-1]) if has_more else None, "has_more": has_more}
    return [lead_out(r) for r in rows], meta


def get_lead(session: Session, ctx: TenantContext, lead_id: uuid.UUID) -> dict:
    return lead_out(_get_scoped(session, ctx, lead_id))


def update_lead(session: Session, ctx: TenantContext, lead_id: uuid.UUID, body: LeadUpdate) -> dict:
    lead = _get_scoped(session, ctx, lead_id)
    changes = body.model_dump(exclude_unset=True)
    reopen_reason = changes.pop("reopen_reason", None)
    new_status = changes.pop("status", None)
    lost_reason = changes.pop("lost_reason", None)
    old_status = lead.status

    if new_status is not None and new_status != old_status:
        check_transition(
            old_status,
            new_status,
            lost_reason=lost_reason,
            is_admin=ctx.role == "admin",
            reopen_reason=reopen_reason,
        )
        lead.status = new_status
        lead.lost_reason = lost_reason if new_status == "lost" else None
        session.add(
            Interaction(
                tenant_id=ctx.tenant_id,
                lead_id=lead.id,
                type="status_change",
                source="manual",
                details={
                    "from": old_status,
                    "to": new_status,
                    "reason": lost_reason or reopen_reason,
                    "actor_user_id": str(ctx.user_id),
                },
            )
        )
        record_audit_event(
            session,
            action="lead.status_changed",
            actor_type="user",
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            entity_type="lead",
            entity_id=lead.id,
            details={"from": old_status, "to": new_status},
        )

    for field, value in changes.items():
        setattr(lead, field, value)

    if lead.email is None and lead.phone is None:
        session.rollback()
        raise AuthError(422, "validation_error", "A lead needs an email or a phone number")

    session.commit()
    session.refresh(lead)
    return lead_out(lead)


def add_note(session: Session, ctx: TenantContext, lead_id: uuid.UUID, body: NoteCreate) -> dict:
    lead = _get_scoped(session, ctx, lead_id)
    note = Interaction(
        tenant_id=ctx.tenant_id,
        lead_id=lead.id,
        type="note",
        source="manual",
        details={"text": body.text, "actor_user_id": str(ctx.user_id)},
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return {
        "id": str(note.id),
        "type": "note",
        "text": body.text,
        "created_at": note.created_at.isoformat(),
    }
