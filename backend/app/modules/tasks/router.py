import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_manager_or_admin
from app.core.tenancy import TenantContext
from app.database.session import get_session
from app.modules.tasks import service
from app.modules.tasks.schemas import TaskApprovalRequest

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.patch("/{task_id}/approval")
def review_task(
    task_id: uuid.UUID,
    body: TaskApprovalRequest,
    context: Annotated[TenantContext, Depends(require_manager_or_admin)],
    session: Session = Depends(get_session),
) -> dict:
    return {"data": service.review_task_approval(session, context, task_id, body)}
