import uuid

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class TemplatePayload(BaseModel):
    """An approved WhatsApp template. Supplying one bypasses the 24-hour window."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=512)
    language: str = Field(min_length=2, max_length=20)
    params: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name", "language")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Template fields cannot be blank")
        return value

    @field_validator("params")
    @classmethod
    def strip_params(cls, value: list[str]) -> list[str]:
        return [str(item) for item in value]


class MessageSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    conversation_id: uuid.UUID
    # "message_text" is accepted for clients built against the earlier schema.
    text: str | None = Field(
        default=None,
        max_length=4096,
        validation_alias=AliasChoices("text", "message_text"),
    )
    template: TemplatePayload | None = None
    task_id: uuid.UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("task_id", "approval_task_id"),
    )

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Message text cannot be blank")
        return value

    @model_validator(mode="after")
    def exactly_one_body(self) -> "MessageSendRequest":
        if (self.text is None) == (self.template is None):
            raise ValueError("Provide exactly one of text or template")
        return self
