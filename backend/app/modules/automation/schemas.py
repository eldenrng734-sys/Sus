import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LeadContextData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    status: str
    assigned_user_id: str | None = None
    team_id: str | None = None
    opted_out: bool = False
    manager_user_ids: list[str] = Field(default_factory=list)


class LeadContextResponse(BaseModel):
    data: LeadContextData


class AutomationMessageSendRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=4096)
    task_id: uuid.UUID | None = None
    approval_task_id: uuid.UUID | None = None


class TaskResultRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["sent", "failed", "skipped", "needs_approval"]
    message_id: uuid.UUID | None = None
    task_status: str | None = None
    note: str | None = None
    error_code: str | None = None
    retryable: bool = False


class AutomationErrorRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workflow_id: str = Field(min_length=1, max_length=100)
    workflow_name: str | None = Field(default=None, max_length=200)
    node_name: str | None = Field(default=None, max_length=200)
    error_class: str = Field(min_length=1, max_length=200)
    error_message: str | None = Field(default=None, max_length=500)
