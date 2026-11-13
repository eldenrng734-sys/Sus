import pytest

from app.modules.leads.capture_normalize import (
    InvalidContact,
    clean_name,
    normalize_email,
    normalize_phone,
)


def test_email_is_trimmed_and_lowercased():
    assert normalize_email("  Ayesha@Example.COM ") == "ayesha@example.com"


def test_blank_email_is_none():
    assert normalize_email("   ") is None
    assert normalize_email(None) is None


def test_invalid_email_raises():
    with pytest.raises(InvalidContact):
        normalize_email("not-an-email")


@pytest.mark.parametrize(
    "raw",
    ["+880 1700-000000", "01700000000", "008801700000000", "8801700000000"],
)
def test_bangladesh_numbers_become_e164(raw):
    assert normalize_phone(raw) == "+8801700000000"


def test_other_country_number_keeps_its_code():
    assert normalize_phone("(+1) 415 555 0100") == "+14155550100"


@pytest.mark.parametrize("raw", ["abc", "123", "+12"])
def test_invalid_phone_raises(raw):
    with pytest.raises(InvalidContact):
        normalize_phone(raw)


def test_blank_phone_is_none():
    assert normalize_phone("  ") is None
    assert normalize_phone(None) is None


def test_name_whitespace_is_collapsed():
    assert clean_name("  Ayesha   Rahman ") == "Ayesha Rahman"


def test_empty_name_raises():
    with pytest.raises(InvalidContact):
        clean_name("   ")