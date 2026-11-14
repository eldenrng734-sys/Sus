import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectIntegrationRequest(BaseModel):
    provider_account_id: str = Field(..., min_length=1, max_length=128)
    access_token: str = Field(..., min_length=1)
    waba_id: str | None = Field(default=None, max_length=128)
    scopes: list[str] = Field(default_factory=list)


class IntegrationItem(BaseModel):
    id: uuid.UUID
    provider: str
    provider_account_id: str
    status: str
    scopes: list[str]
    created_at: datetime
    connected: bool = True

    model_config = {"from_attributes": True}


class ConnectIntegrationResponse(BaseModel):
    connected: bool = True
    id: uuid.UUID
    provider: str
    provider_account_id: str
    status: str
    scopes: list[str]


class DisconnectIntegrationResponse(BaseModel):
    connected: bool = False
    id: uuid.UUID
    status: str

