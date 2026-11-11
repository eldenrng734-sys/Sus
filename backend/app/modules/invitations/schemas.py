import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["rep", "manager", "admin"]


class InviteRequest(BaseModel):
    email: EmailStr
    role: Role


class AcceptRequest(BaseModel):
    token: str
    full_name: str | None = Field(default=None, max_length=200)
    # Only needed for a brand-new user. An existing user keeps their old password.
    password: str | None = Field(default=None, min_length=8, max_length=128)


class ChangeRoleRequest(BaseModel):
    role: Role


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
