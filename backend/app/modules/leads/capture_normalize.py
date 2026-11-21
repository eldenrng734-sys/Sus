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


_EMAIL_IN_TEXT_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Labeled phone: "phone: 017...", "phn is ...", "call me at ...", "mobile no ...", "whatsapp 017..."
_PHONE_LABEL_RE = re.compile(
    r"\b(?:phone|phn|mobile|cell(?:phone)?|call|tel|contact|num|number|whatsapp|wa)\b"
    r"(?:\s*(?:number|no\.?))?(?:\s+(?:is|at|me))?\s*[:=-]?\s*"
    r"([+\d][\d\s()./-]{6,}\d)",
    re.IGNORECASE,
)

# Bangladeshi 11-digit mobile format: 013-019 followed by 8 digits (optionally with +88 or 0088)
_BD_MOBILE_RE = re.compile(
    r"(?<!\d)(?:(?:\+?880\s?|00880\s?)|0)1[3-9][\d\s.-]{8,10}(?!\d)"
)

# Explicit E.164 international phone format, with optional spaces and punctuation.
_INTL_PHONE_RE = re.compile(
    r"(?<!\d)\+[1-9][\d\s()./-]{6,16}\d(?!\d)"
)


def extract_message_phone(text: str | None) -> str | None:
    """Extract and normalize a phone number from chat message text.

    Supports:
    1. Explicitly labeled phone numbers (phone:, phn number, mobile is, call at, etc.)
    2. Standard 11-digit Bangladeshi mobile numbers (013-019...)
    3. Explicit international phone numbers (+...)
    """
    if not text:
        return None

    # 1. Check labeled phone pattern first
    match = _PHONE_LABEL_RE.search(text)
    if match:
        try:
            return normalize_phone(match.group(1))
        except InvalidContact:
            pass

    # 2. Check Bangladeshi mobile number pattern (unambiguous 11-digit mobile starting with 01)
    for bd_match in _BD_MOBILE_RE.finditer(text):
        try:
            return normalize_phone(bd_match.group(0))
        except InvalidContact:
            pass

    # 3. Check international phone pattern
    for intl_match in _INTL_PHONE_RE.finditer(text):
        try:
            return normalize_phone(intl_match.group(0))
        except InvalidContact:
            pass

    return None


def extract_message_email(text: str | None) -> str | None:
    """Extract and normalize an email address from chat message text."""
    if not text:
        return None
    match = _EMAIL_IN_TEXT_RE.search(text)
    if not match:
        return None
    try:
        return normalize_email(match.group(0))
    except InvalidContact:
        return None
