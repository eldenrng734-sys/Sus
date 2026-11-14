import uuid
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member, require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.auth.errors import AuthError
from app.modules.leads import crud, csv_import, service
from app.modules.leads.schemas import (
    LeadAssignRequest,
    LeadAutoAssignRequest,
    LeadCreate,
    LeadUpdate,
    NoteCreate,
)

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


@router.post("", status_code=201)
def post_lead(
    body: LeadCreate,
    response: Response,
    context: Annotated[TenantContext, Depends(require_any_member)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    session: Session = Depends(get_session),
) -> dict:
    data, replay = crud.create_lead(session, context, body, idempotency_key)
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return {"data": data}


@router.post("/import", status_code=200)
def import_leads(
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    file: Annotated[UploadFile, File()],
    dry_run: Annotated[bool, Form()] = False,
    session: Session = Depends(get_session),
) -> dict:
    filename = (file.filename or "").lower()

    if not filename.endswith(".csv") and file.content_type not in {
        "text/csv",
        "text/plain",
    }:
        raise AuthError(
            415,
            "unsupported_media_type",
            "Upload a .csv file",
        )

    raw = file.file.read(csv_import.MAX_BYTES + 1)

    try:
        data = csv_import.import_csv(
            session=session,
            ctx=context,
            raw=raw,
            dry_run=dry_run,
            idempotency_key=idempotency_key,
        )
        return {"data": data}
    finally:
        file.file.close()


@router.get("")
def get_leads(
    request: Request,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    q: str | None = Query(default=None, max_length=100),
    status: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    priority: str | None = None,
    assigned_user_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "-created_at",
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    allowed_filters = {
        "q",
        "status",
        "source",
        "priority",
        "assigned_user_id",
        "team_id",
        "created_from",
        "created_to",
        "sort",
        "limit",
        "cursor",
    }
    unknown_filters = set(request.query_params.keys()) - allowed_filters
    if unknown_filters:
        raise AuthError(
            422,
            "validation_error",
            f"Unknown lead filter: {sorted(unknown_filters)[0]}",
        )

    data, meta = crud.list_leads(
        session=session,
        ctx=context,
        q=q,
        status=status,
        source=source,
        priority=priority,
        assigned_user_id=assigned_user_id,
        team_id=team_id,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
        limit=limit,
        cursor=cursor,
    )
    return {"data": data, "meta": meta}


@router.get("/{lead_id}")
def get_lead_detail(
    lead_id: uuid.UUID,
    request: Request,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    include: list[str] | None = Query(default=None),
) -> dict:
    unknown_filters = set(request.query_params.keys()) - {"include"}
    if unknown_filters:
        raise AuthError(
            422,
            "validation_error",
            f"Unknown lead expansion parameter: {sorted(unknown_filters)[0]}",
        )
    return {"data": crud.get_lead(session, context, lead_id, include)}


@router.patch("/{lead_id}")
def patch_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": crud.update_lead(session, context, lead_id, body)}


@router.post("/{lead_id}/notes", status_code=201)
def post_note(
    lead_id: uuid.UUID,
    body: NoteCreate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": crud.add_note(session, context, lead_id, body)}


@router.post("/{lead_id}/assign")
def post_assign_lead(
    lead_id: uuid.UUID,
    body: LeadAssignRequest,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.assign_lead(session, context, lead_id, body)}


@router.post("/{lead_id}/auto-assign")
def post_auto_assign_lead(
    lead_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
    body: LeadAutoAssignRequest | None = None,
) -> dict:
    return {
        "data": service.auto_assign_lead(
            session,
            context,
            lead_id,
            body.team_id if body else None,
        )
    }
