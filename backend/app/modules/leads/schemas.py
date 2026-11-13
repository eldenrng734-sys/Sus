<<<<<<< HEAD
=======
import re
>>>>>>> origin/dev
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

<<<<<<< HEAD

class LeadAssignRequest(BaseModel):
=======
LeadSource = Literal[
    "website_form",
    "tracking",
    "whatsapp",
    "facebook_lead_ads",
    "messenger",
    "manual",
    "csv",
]
LeadStatus = Literal["new", "contacted", "qualified", "proposal", "won", "lost"]
LeadPriority = Literal["low", "medium", "high"]
LostReason = Literal["price", "timing", "no_response", "competitor", "not_qualified", "other"]


class LeadAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

>>>>>>> origin/dev
    assigned_user_id: uuid.UUID
    team_id: uuid.UUID


def _clean_phone(value: str | None) -> str | None:
    if value is None:
        return None
<<<<<<< HEAD
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    return cleaned or None
=======
    raw = value.strip()
    if not re.fullmatch(r"[0-9+\s().-]+", raw):
        raise ValueError("Phone number contains unsupported characters")
    cleaned = re.sub(r"[^0-9+]", "", raw)
    if not cleaned:
        return None
    if cleaned.count("+") > 1 or ("+" in cleaned and not cleaned.startswith("+")):
        raise ValueError("Phone number may contain one leading + only")
    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise ValueError("Phone number must contain between 7 and 15 digits")
    return cleaned


def _lower_email(value: EmailStr | None) -> EmailStr | None:
    return str(value).strip().lower() if value else None
>>>>>>> origin/dev


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=200)
<<<<<<< HEAD
    consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.strip().lower() if value else None
=======
    source: LeadSource = "manual"
    source_campaign: str | None = Field(default=None, max_length=200)
    external_id: str | None = Field(default=None, max_length=200)
    consent: bool = False
    assigned_user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "company_name", "source_campaign", "external_id", "notes")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return _lower_email(value)
>>>>>>> origin/dev

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value):
        return _clean_phone(value)

    @model_validator(mode="after")
<<<<<<< HEAD
    def need_contact(self):
        if not self.email and not self.phone:
            raise ValueError("Provide an email or a phone number")
=======
    def need_contact_and_valid_name(self):
        if not self.name.strip():
            raise ValueError("Name cannot be blank")
        if not self.email and not self.phone:
            raise ValueError("Provide an email or a phone number")
        if self.external_id is not None and not self.external_id:
            raise ValueError("external_id cannot be blank")
>>>>>>> origin/dev
        return self


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

<<<<<<< HEAD
=======
    version: int = Field(ge=1)
>>>>>>> origin/dev
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=200)
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["new", "contacted", "qualified", "proposal", "won", "lost"] | None = None
    lost_reason: str | None = None
    reopen_reason: str | None = Field(default=None, max_length=500)
<<<<<<< HEAD
=======
    priority: LeadPriority | None = None
    status: LeadStatus | None = None
    lost_reason: LostReason | None = None
    reopen_reason: str | None = Field(default=None, max_length=500)
    assigned_user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None

    @field_validator("name", "company_name", "reopen_reason")
    @classmethod
    def strip_optional_text(cls, value):
        return value.strip() if isinstance(value, str) else value
>>>>>>> origin/dev

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.strip().lower() if value else None
<<<<<<< HEAD
=======
        return _lower_email(value)
>>>>>>> origin/dev

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value):
        return _clean_phone(value)

<<<<<<< HEAD
=======
    @model_validator(mode="after")
    def validate_patch(self):
        changed = self.model_fields_set - {"version", "reopen_reason"}
        if not changed:
            raise ValueError("Provide at least one field to update")
        if "name" in self.model_fields_set and (self.name is None or not self.name.strip()):
            raise ValueError("Name cannot be blank")
        if self.lost_reason is not None and self.status != "lost":
            raise ValueError("lost_reason may only be supplied when status is lost")
        if self.reopen_reason is not None and self.status != "contacted":
            raise ValueError("reopen_reason may only be supplied when reopening to contacted")
        return self

>>>>>>> origin/dev

class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
<<<<<<< HEAD
=======

    @field_validator("text")
    @classmethod
    def strip_note(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be blank")
        return value
>>>>>>> origin/dev
