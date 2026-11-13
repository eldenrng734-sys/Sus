"""Pure helpers that clean lead contact data before dedupe. No database access."""

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Assumption to confirm with the team: numbers starting with a single 0 are Bangladeshi.
DEFAULT_COUNTRY_CODE = "880"


class InvalidContact(ValueError):
    """Raised when a name, email or phone value cannot be used."""


def clean_name(value: str | None) -> str:
    name = " ".join((value or "").split())
    if not name:
        raise InvalidContact("name is required")
    return name


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    email = value.strip().lower()
    if not email:
        return None
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise InvalidContact("invalid email")
    return email


def normalize_phone(
    value: str | None, default_country_code: str = DEFAULT_COUNTRY_CODE
) -> str | None:
    """Return the number in E.164 form (+8801700000000) or None if blank."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    has_plus = raw.lstrip("( ").startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise InvalidContact("invalid phone")
    if not has_plus:
        if digits.startswith("00"):
            digits = digits[2:]
        elif digits.startswith("0"):
            digits = default_country_code + digits[1:]
        elif len(digits) < 11:
            raise InvalidContact("phone needs a country code")
    if not 8 <= len(digits) <= 15:
        raise InvalidContact("invalid phone length")
    return "+" + digits
