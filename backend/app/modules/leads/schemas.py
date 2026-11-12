import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


LeadSource = Literal[
    "website_form",
    "tracking",
    "whatsapp",
    "facebook_lead_ads",
    "messenger",
    "manual",
    "csv",
]


class LeadAssignRequest(BaseModel):
    assigned_user_id: uuid.UUID
    team_id: uuid.UUID


def _clean_phone(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    return cleaned or None


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=200)
    source: LeadSource = "manual"
    source_campaign: str | None = Field(default=None, max_length=200)
    external_id: str | None = Field(default=None, max_length=255)
    consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.strip().lower() if value else None

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value):
        return _clean_phone(value)

    @field_validator("source_campaign", "external_id")
    @classmethod
    def strip_optional_strings(cls, value):
        return value.strip() or None if value else None

    @model_validator(mode="after")
    def need_contact(self):
        if not self.email and not self.phone:
            raise ValueError("Provide an email or a phone number")
        return self


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=200)
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["new", "contacted", "qualified", "proposal", "won", "lost"] | None = None
    lost_reason: str | None = None
    reopen_reason: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.strip().lower() if value else None

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value):
        return _clean_phone(value)


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
