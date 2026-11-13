import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, asc, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import apply_data_scope
from app.core.tenancy import TenantContext
from app.modules.audit.service import record_audit_event
from app.modules.auth.errors import AuthError
from app.modules.idempotency.models import IdempotencyKey
from app.modules.leads.models import Interaction, Lead
from app.modules.leads.schemas import LeadCreate, LeadUpdate, NoteCreate
from app.modules.leads.transitions import check_transition
from app.modules.tenants.models import Team, TenantMembership
from app.modules.users.models import User

LIMIT_MAX = 100
IDEMPOTENCY_TTL = timedelta(hours=24)
CREATE_LEAD_PATH = "/api/v1/leads"
VALID_STATUSES = {"new", "contacted", "qualified", "proposal", "won", "lost"}
VALID_SOURCES = {
    "website_form",
    "tracking",
    "whatsapp",
    "facebook_lead_ads",
    "messenger",
    "manual",
    "csv",
}
VALID_PRIORITIES = {"low", "medium", "high"}
SORT_FIELDS = {"created_at", "updated_at", "lead_score", "priority"}


def lead_out(lead: Lead) -> dict:
    return {
        "id": str(lead.id),
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "company_name": lead.company_name,
        "source": lead.source,
        "source_campaign": lead.source_campaign,
        "external_id": lead.external_id,
        "status": lead.status,
        "lost_reason": lead.lost_reason,
        "assigned_user_id": str(lead.assigned_user_id) if lead.assigned_user_id else None,
        "team_id": str(lead.team_id) if lead.team_id else None,
        "intent": lead.intent,
        "lead_score": lead.lead_score,
        "priority": lead.priority,
        "consent": lead.consent,
        "opted_out": lead.opted_out,
        "version": lead.version,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
    }


def _request_hash(body: LeadCreate) -> str:
    normalized = body.model_dump(mode="json")
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _claim_create_idempotency(
    session: Session,
    ctx: TenantContext,
    key: str,
    request_hash: str,
) -> tuple[uuid.UUID | None, dict[str, Any] | None]:
    """Claim a request key, or return the previously stored response.

    The PostgreSQL upsert also lets an expired 24-hour key be safely reused.
    A concurrent request with the same key waits on the unique index and then
    observes the first request's committed response.
    """
    now = datetime.now(UTC)
    statement = (
        pg_insert(IdempotencyKey)
        .values(
            tenant_id=ctx.tenant_id,
            caller_type="user",
            caller_id=str(ctx.user_id),
            method="POST",
            path=CREATE_LEAD_PATH,
            key=key,
            request_hash=request_hash,
            expires_at=now + IDEMPOTENCY_TTL,
        )
        .on_conflict_do_update(
            constraint="uq_idempotency_keys_scope",
            set_={
                "request_hash": request_hash,
                "response_status": None,
                "response_body": None,
                "expires_at": now + IDEMPOTENCY_TTL,
            },
            where=IdempotencyKey.expires_at <= func.now(),
        )
        .returning(IdempotencyKey.id)
    )
    claimed_id = session.scalar(statement)
    if claimed_id is not None:
        return claimed_id, None

    existing = session.scalar(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.tenant_id == ctx.tenant_id,
            IdempotencyKey.caller_type == "user",
            IdempotencyKey.caller_id == str(ctx.user_id),
            IdempotencyKey.method == "POST",
            IdempotencyKey.path == CREATE_LEAD_PATH,
            IdempotencyKey.key == key,
        )
        .with_for_update()
    )
    if existing is None:
        raise AuthError(409, "idempotency_conflict", "Could not claim this idempotency key")
    if existing.request_hash != request_hash:
        raise AuthError(
            409,
            "idempotency_conflict",
            "This idempotency key was already used with a different request",
        )
    if existing.response_status is None or existing.response_body is None:
        raise AuthError(
            409,
            "idempotency_in_progress",
            "A request with this idempotency key is still being processed",
        )
    return None, existing.response_body


def _store_create_response(
    session: Session,
    idempotency_id: uuid.UUID,
    response_body: dict[str, Any],
) -> None:
    encoded = json.dumps(response_body, separators=(",", ":"), default=str).encode("utf-8")
    if len(encoded) > 64 * 1024:
        raise AuthError(500, "internal_error", "Idempotent response exceeded the storage limit")
    session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.id == idempotency_id)
        .values(response_status=201, response_body=response_body)
    )


def _get_scoped(
    session: Session,
    ctx: TenantContext,
    lead_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Lead:
    """404 when the lead is outside the caller's scope or company."""
    statement = apply_data_scope(select(Lead).where(Lead.id == lead_id), Lead, ctx)
    if for_update:
        statement = statement.with_for_update()
    lead = session.scalar(statement)
    if lead is None:
        raise AuthError(404, "not_found", "Lead not found")
    return lead


def _validate_assignment(
    session: Session,
    ctx: TenantContext,
    assigned_user_id: uuid.UUID | None,
    team_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if ctx.role == "rep":
        raise AuthError(403, "forbidden", "Only managers and admins can assign leads")

    if ctx.role == "manager":
        if ctx.team_id is None:
            raise AuthError(403, "forbidden", "Your account is not assigned to a team")
        if team_id is not None and team_id != ctx.team_id:
            raise AuthError(403, "forbidden", "You can only assign leads in your team")
        team_id = ctx.team_id

    if team_id is not None:
        team_exists = session.scalar(
            select(Team.id).where(
                Team.id == team_id,
                Team.tenant_id == ctx.tenant_id,
            )
        )
        if team_exists is None:
            raise AuthError(422, "invalid_team", "Team does not belong to this company")

    if assigned_user_id is not None:
        if team_id is None:
            raise AuthError(422, "invalid_assignee", "A team is required when assigning a lead")
        membership = session.scalar(
            select(TenantMembership)
            .join(User, User.id == TenantMembership.user_id)
            .where(
                TenantMembership.tenant_id == ctx.tenant_id,
                TenantMembership.user_id == assigned_user_id,
                TenantMembership.team_id == team_id,
                TenantMembership.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
        if membership is None:
            raise AuthError(
                422,
                "invalid_assignee",
                "Target user must be an active member of the selected team",
            )

    return assigned_user_id, team_id


def _check_duplicate(
    session: Session,
    ctx: TenantContext,
    *,
    email: str | None,
    phone: str | None,
    source: str | None = None,
    external_id: str | None = None,
    exclude_lead_id: uuid.UUID | None = None,
) -> None:
    clauses = []
    if email:
        clauses.append(func.lower(Lead.email) == email.lower())
    if phone:
        clauses.append(Lead.phone == phone)
    if source and external_id:
        clauses.append(and_(Lead.source == source, Lead.external_id == external_id))
    if not clauses:
        return

    statement = select(Lead.id).where(
        Lead.tenant_id == ctx.tenant_id,
        or_(*clauses),
    )
    if exclude_lead_id is not None:
        statement = statement.where(Lead.id != exclude_lead_id)
    existing_id = session.scalar(statement.limit(1))
    if existing_id is not None:
        visible_id = session.scalar(
            apply_data_scope(
                select(Lead.id).where(Lead.id == existing_id),
                Lead,
                ctx,
            )
        )
        details = (
            [{"existing_lead_id": str(existing_id)}]
            if visible_id is not None
            else []
        )
        raise AuthError(
            409,
            "duplicate_lead",
            "A lead with this email, phone, or external ID already exists",
            details=details,
        )


def create_lead(
    session: Session,
    ctx: TenantContext,
    body: LeadCreate,
    idempotency_key: str,
) -> tuple[dict, bool]:
    """Create one tenant-scoped lead; return (response data, is_idempotent_replay)."""
    idempotency_id = None
    try:
        idempotency_id, replay_body = _claim_create_idempotency(
            session, ctx, idempotency_key, _request_hash(body)
        )
        if replay_body is not None:
            return replay_body, True

        _check_duplicate(
            session,
            ctx,
            email=str(body.email) if body.email else None,
            phone=body.phone,
            source=body.source,
            external_id=body.external_id,
        )

        if ctx.role == "rep":
            if body.assigned_user_id is not None or body.team_id is not None:
                raise AuthError(403, "forbidden", "Reps cannot choose a lead owner or team")
            assigned_user_id, team_id = ctx.user_id, ctx.team_id
        elif body.assigned_user_id is not None or body.team_id is not None:
            assigned_user_id, team_id = _validate_assignment(
                session, ctx, body.assigned_user_id, body.team_id
            )
        elif ctx.role == "manager":
            assigned_user_id, team_id = _validate_assignment(
                session, ctx, None, ctx.team_id
            )
        else:
            assigned_user_id, team_id = None, None

        lead = Lead(
            tenant_id=ctx.tenant_id,
            name=body.name,
            email=str(body.email) if body.email else None,
            phone=body.phone,
            company_name=body.company_name,
            source=body.source,
            source_campaign=body.source_campaign,
            external_id=body.external_id,
            priority="medium",
            consent=body.consent,
            version=1,
            consent_at=datetime.now(UTC) if body.consent else None,
            consent_source="manual" if body.consent else None,
            assigned_user_id=assigned_user_id,
            team_id=team_id,
        )
        session.add(lead)
        session.flush()
        session.refresh(lead)

        session.add(
            Interaction(
                tenant_id=ctx.tenant_id,
                lead_id=lead.id,
                type="lead_created",
                source=body.source,
                details={"actor_user_id": str(ctx.user_id)},
                created_by_user_id=ctx.user_id,
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
                    created_by_user_id=ctx.user_id,
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
            details={"source": body.source, "has_initial_note": bool(body.notes)},
        )

        result = lead_out(lead)
        _store_create_response(session, idempotency_id, result)
        session.commit()
        return result, False
    except IntegrityError as exc:
        session.rollback()
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint_name == "uq_leads_tenant_source_external":
            raise AuthError(
                409,
                "duplicate_lead",
                "A lead with this source and external ID already exists",
            ) from exc
        raise
    except Exception:
        session.rollback()
        raise


def _split_multi(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [part.strip() for value in values for part in value.split(",") if part.strip()]


def _cursor_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in {"created_at", "updated_at"}:
        return value.isoformat()
    return value


def _encode_cursor(lead: Lead, sort_field: str, descending: bool) -> str:
    payload = {
        "sort": sort_field,
        "descending": descending,
        "value": _cursor_value(sort_field, getattr(lead, sort_field)),
        "id": str(lead.id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str,
    sort_field: str,
    descending: bool,
) -> tuple[Any, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if payload.get("sort") != sort_field or payload.get("descending") is not descending:
            raise ValueError("cursor does not match sort")
        lead_id = uuid.UUID(payload["id"])
        value = payload.get("value")
        if value is not None:
            if sort_field in {"created_at", "updated_at"}:
                value = datetime.fromisoformat(value)
            elif sort_field == "lead_score":
                value = int(value)
            elif sort_field == "priority":
                if value not in VALID_PRIORITIES:
                    raise ValueError("invalid priority cursor")
        return value, lead_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AuthError(400, "bad_request", "Invalid cursor") from exc


def list_leads(
    session: Session,
    ctx: TenantContext,
    q: str | None = None,
    status: list[str] | None = None,
    source: list[str] | None = None,
    priority: str | None = None,
    assigned_user_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "-created_at",
    limit: int = 25,
    cursor: str | None = None,
) -> tuple[list[dict], dict]:
    limit = max(1, min(limit, LIMIT_MAX))
    q = q.strip() if q else None
    if q and len(q) > 100:
        raise AuthError(422, "validation_error", "Search text is too long (max 100)")

    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    if sort_field not in SORT_FIELDS:
        raise AuthError(422, "validation_error", "Unsupported lead sort field")

    statuses = _split_multi(status)
    sources = _split_multi(source)
    if any(value not in VALID_STATUSES for value in statuses):
        raise AuthError(422, "validation_error", "Unsupported lead status filter")
    if any(value not in VALID_SOURCES for value in sources):
        raise AuthError(422, "validation_error", "Unsupported lead source filter")
    if priority is not None and priority not in VALID_PRIORITIES:
        raise AuthError(422, "validation_error", "Unsupported lead priority filter")
    for field_name, value in (
        ("created_from", created_from),
        ("created_to", created_to),
    ):
        if value is not None and value.utcoffset() is None:
            raise AuthError(
                422,
                "validation_error",
                f"{field_name} must include a timezone offset",
            )
    if created_from and created_to and created_from > created_to:
        raise AuthError(422, "validation_error", "created_from must be before created_to")

    statement = apply_data_scope(select(Lead), Lead, ctx)

    if q:
        safe = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe}%"
        statement = statement.where(
            or_(
                Lead.name.ilike(pattern, escape="\\"),
                Lead.email.ilike(pattern, escape="\\"),
                Lead.phone.ilike(pattern, escape="\\"),
                Lead.company_name.ilike(pattern, escape="\\"),
            )
        )
    if statuses:
        statement = statement.where(Lead.status.in_(statuses))
    if sources:
        statement = statement.where(Lead.source.in_(sources))
    if priority:
        statement = statement.where(Lead.priority == priority)
    if assigned_user_id:
        statement = statement.where(Lead.assigned_user_id == assigned_user_id)
    if team_id:
        statement = statement.where(Lead.team_id == team_id)
    if created_from:
        statement = statement.where(Lead.created_at >= created_from)
    if created_to:
        statement = statement.where(Lead.created_at <= created_to)

    sort_column = getattr(Lead, sort_field)
    if cursor:
        value, cursor_id = _decode_cursor(cursor, sort_field, descending)
        id_comparison = Lead.id < cursor_id if descending else Lead.id > cursor_id
        if value is None:
            statement = statement.where(sort_column.is_(None), id_comparison)
        else:
            value_comparison = sort_column < value if descending else sort_column > value
            statement = statement.where(
                or_(
                    value_comparison,
                    and_(sort_column == value, id_comparison),
                    sort_column.is_(None),
                )
            )

    order_column = desc(sort_column) if descending else asc(sort_column)
    tie_breaker = desc(Lead.id) if descending else asc(Lead.id)
    statement = statement.order_by(order_column.nulls_last(), tie_breaker)
    rows = session.scalars(statement.limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        _encode_cursor(rows[-1], sort_field, descending)
        if has_more and rows
        else None
    )
    return (
        [lead_out(row) for row in rows],
        {"next_cursor": next_cursor, "has_more": has_more},
    )


def get_lead(
    session: Session,
    ctx: TenantContext,
    lead_id: uuid.UUID,
    include: list[str] | None = None,
) -> dict:
    lead = _get_scoped(session, ctx, lead_id)
    requested = set(_split_multi(include) if include is not None else ["latest_assessment"])
    allowed = {"owner", "team", "latest_assessment", "next_task"}
    unknown = requested - allowed
    if unknown:
        raise AuthError(422, "validation_error", "Unsupported lead expansion")

    result = lead_out(lead)
    if "owner" in requested:
        owner = (
            session.scalar(select(User).where(User.id == lead.assigned_user_id))
            if lead.assigned_user_id
            else None
        )
        result["owner"] = (
            {
                "id": str(owner.id),
                "email": owner.email,
                "full_name": owner.full_name,
            }
            if owner
            else None
        )
    if "team" in requested:
        team = (
            session.scalar(
                select(Team).where(
                    Team.id == lead.team_id,
                    Team.tenant_id == ctx.tenant_id,
                )
            )
            if lead.team_id
            else None
        )
        result["team"] = {"id": str(team.id), "name": team.name} if team else None
    if "latest_assessment" in requested:
        from app.modules.ai.models import LeadAssessment

        assessment = session.scalar(
            select(LeadAssessment)
            .where(
                LeadAssessment.tenant_id == ctx.tenant_id,
                LeadAssessment.lead_id == lead.id,
            )
            .order_by(LeadAssessment.created_at.desc(), LeadAssessment.id.desc())
            .limit(1)
        )
        result["latest_assessment"] = (
            {
                "id": str(assessment.id),
                "intent": assessment.intent,
                "priority": assessment.priority,
                "lead_score": assessment.lead_score,
                "confidence": (
                    float(assessment.confidence) if assessment.confidence is not None else None
                ),
                "needs_human_review": assessment.needs_human_review,
                "review_status": assessment.review_status,
                "status": assessment.status,
                "summary": assessment.summary,
                "model": assessment.model,
                "prompt_version": assessment.prompt_version,
                "created_at": assessment.created_at.isoformat(),
            }
            if assessment
            else None
        )
    if "next_task" in requested:
        from app.modules.tasks.models import Task

        task = session.scalar(
            select(Task)
            .where(
                Task.tenant_id == ctx.tenant_id,
                Task.lead_id == lead.id,
                Task.status == "open",
            )
            .order_by(Task.due_at.asc(), Task.id.asc())
            .limit(1)
        )
        result["next_task"] = (
            {
                "id": str(task.id),
                "title": task.title,
                "type": task.type,
                "status": task.status,
                "due_at": task.due_at.isoformat(),
                "assigned_user_id": (
                    str(task.assigned_user_id) if task.assigned_user_id else None
                ),
                "version": task.version,
            }
            if task
            else None
        )
    return result


def update_lead(
    session: Session,
    ctx: TenantContext,
    lead_id: uuid.UUID,
    body: LeadUpdate,
) -> dict:
    try:
        lead = _get_scoped(session, ctx, lead_id, for_update=True)
        if lead.version != body.version:
            raise AuthError(409, "version_conflict", "Lead was changed by another request")

        changes = body.model_dump(exclude_unset=True, exclude={"version"})
        reopen_reason = changes.pop("reopen_reason", None)
        new_status = changes.pop("status", None)
        lost_reason = changes.pop("lost_reason", None)
        assignment_requested = "assigned_user_id" in changes or "team_id" in changes
        requested_assignee = changes.pop("assigned_user_id", lead.assigned_user_id)
        requested_team = changes.pop("team_id", lead.team_id)
        old_status = lead.status
        changed_fields = set(changes)

        if "email" in changes or "phone" in changes:
            _check_duplicate(
                session,
                ctx,
                email=str(changes["email"]) if changes.get("email") else None,
                phone=changes.get("phone"),
                exclude_lead_id=lead.id,
            )

        if assignment_requested:
            assigned_user_id, team_id = _validate_assignment(
                session, ctx, requested_assignee, requested_team
            )
            lead.assigned_user_id = assigned_user_id
            lead.team_id = team_id
            session.add(
                Interaction(
                    tenant_id=ctx.tenant_id,
                    lead_id=lead.id,
                    type="assignment",
                    source="manual",
                    details={
                        "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
                        "team_id": str(team_id) if team_id else None,
                        "actor_user_id": str(ctx.user_id),
                    },
                    created_by_user_id=ctx.user_id,
                )
            )
            changed_fields.update({"assigned_user_id", "team_id"})

        if reopen_reason is not None and not (
            old_status == "lost" and new_status == "contacted"
        ):
            raise AuthError(
                422,
                "validation_error",
                "reopen_reason is only valid when an admin reopens a lost lead",
            )

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
                    created_by_user_id=ctx.user_id,
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
                details={
                    "from": old_status,
                    "to": new_status,
                    "reason": lost_reason or reopen_reason,
                },
            )
            changed_fields.add("status")
            if new_status == "lost":
                changed_fields.add("lost_reason")
        elif lost_reason is not None:
            if lead.status != "lost":
                raise AuthError(422, "validation_error", "lost_reason requires status='lost'")
            lead.lost_reason = lost_reason
            changed_fields.add("lost_reason")

        for field, value in changes.items():
            if field not in {"assigned_user_id", "team_id"}:
                setattr(lead, field, value)

        if lead.email is None and lead.phone is None:
            raise AuthError(422, "validation_error", "A lead needs an email or a phone number")
        if lead.name is None or not lead.name.strip():
            raise AuthError(422, "validation_error", "A lead needs a name")

        if changed_fields or assignment_requested:
            lead.version += 1
            general_changes = changed_fields - {"status", "lost_reason"}
            if general_changes or assignment_requested or (
                lost_reason is not None and new_status == old_status
            ):
                record_audit_event(
                    session,
                    action="lead.updated",
                    actor_type="user",
                    tenant_id=ctx.tenant_id,
                    actor_user_id=ctx.user_id,
                    entity_type="lead",
                    entity_id=lead.id,
                    details={"changed_fields": sorted(changed_fields)},
                )

        session.commit()
        session.refresh(lead)
        return lead_out(lead)
    except Exception:
        session.rollback()
        raise


def add_note(session: Session, ctx: TenantContext, lead_id: uuid.UUID, body: NoteCreate) -> dict:
    try:
        lead = _get_scoped(session, ctx, lead_id)
        note = Interaction(
            tenant_id=ctx.tenant_id,
            lead_id=lead.id,
            type="note",
            source="manual",
            details={"text": body.text, "actor_user_id": str(ctx.user_id)},
            created_by_user_id=ctx.user_id,
        )
        session.add(note)
        session.flush()
        session.refresh(note)
        record_audit_event(
            session,
            action="lead.note_added",
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
            details={"interaction_id": str(note.id)},
        )
        result = {
            "id": str(note.id),
            "type": "note",
            "text": body.text,
            "created_at": note.created_at.isoformat(),
        }
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
