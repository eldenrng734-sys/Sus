from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class FormUtm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str | None = Field(default=None, max_length=255)
    medium: str | None = Field(default=None, max_length=255)
    campaign: str | None = Field(default=None, max_length=255)
    term: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, max_length=255)

    @field_validator("source", "medium", "campaign", "term", "content")
    @classmethod
    def strip_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class PublicFormSubmission(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=2000)
    consent: bool
    consent_version: str | None = Field(default=None, max_length=50)
    utm: FormUtm | None = None
    honeypot: str = Field(default="", max_length=255, alias="_hp")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("phone", "company_name", "message")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip().lower()
            return value or None
        return value

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Consent is required")
        return value
