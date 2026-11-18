import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    member_count: int = 0


class TenantListResponse(BaseModel):
    data: list[TenantSummary]


class TenantDetailResponse(BaseModel):
    data: TenantSummary


class TenantUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended"] = Field(
        description="Target status for tenant"
    )


class PlatformHealth(BaseModel):
    db_connections: int
    dead_outbox_count: int
    status: str = "ok"


class PlatformHealthResponse(BaseModel):
    data: PlatformHealth
