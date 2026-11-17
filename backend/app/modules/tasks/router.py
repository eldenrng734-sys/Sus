
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_any_member, require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.tasks import service
from app.modules.tasks.schemas import (
    TaskApprovalDecision,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
def get_tasks(
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    tasks = service.list_tasks(
        session, context, limit=limit, offset=offset
    )
    return {"data": [TaskOut.model_validate(task) for task in tasks]}


@router.post("", status_code=201)
def post_task(
    body: TaskCreate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    task = service.create_task(session, context, body)
    return {"data": TaskOut.model_validate(task)}


@router.get("/approval-queue")
def get_approval_queue(
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    tasks = service.list_approval_queue(
        session, context, limit=limit, offset=offset
    )
    return {"data": [TaskOut.model_validate(task) for task in tasks]}


@router.post("/{task_id}/approve")
def approve_task(
    task_id: uuid.UUID,
    body: TaskApprovalDecision,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    task = service.decide_task_approval(
        session,
        context,
        task_id,
        approved=True,
        note=body.note,
    )
    return {"data": TaskOut.model_validate(task)}


@router.post("/{task_id}/reject")
def reject_task(
    task_id: uuid.UUID,
    body: TaskApprovalDecision,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    task = service.decide_task_approval(
        session,
        context,
        task_id,
        approved=False,
        note=body.note,
    )
    return {"data": TaskOut.model_validate(task)}


@router.get("/{task_id}")
def get_task_detail(
    task_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    task = service.get_task(session, context, task_id)
    return {"data": TaskOut.model_validate(task)}


@router.patch("/{task_id}")
def patch_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    context: Annotated[TenantContext, Depends(require_any_member)],
    session: Session = Depends(get_session),
) -> dict:
    task = service.update_task(session, context, task_id, body)
    return {"data": TaskOut.model_validate(task)}
