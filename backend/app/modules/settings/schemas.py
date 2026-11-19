import re
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class AutomationSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    quiet_hours_start: str
    quiet_hours_end: str


class AutomationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    quiet_hours_start: str
    quiet_hours_end: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception as exc:
            raise ValueError(f"Invalid timezone: {v}") from exc
        return v

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("Time must be formatted as HH:MM in 24-hour time")
        return v
