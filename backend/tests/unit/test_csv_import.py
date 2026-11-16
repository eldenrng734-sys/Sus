import pytest

from app.modules.auth.errors import AuthError
from app.modules.leads.csv_import import MAX_ROWS, neutralize, parse_csv


def test_formula_cells_are_neutralized():
    assert neutralize("=SUM(A1)") == "'=SUM(A1)"
    assert neutralize("@cmd") == "'@cmd"
    assert neutralize("  Ayesha ") == "Ayesha"


def test_parse_needs_name_and_contact_columns():
    with pytest.raises(AuthError):
        parse_csv(b"email\na@example.com\n")
    with pytest.raises(AuthError):
        parse_csv(b"name\nAyesha\n")


def test_parse_skips_empty_rows_and_numbers_from_two():
    rows = parse_csv(b"Name,Email\nAyesha,a@example.com\n,\nRahim,r@example.com\n")
    assert [n for n, _ in rows] == [2, 4]
    assert rows[0][1]["name"] == "Ayesha"


def test_utf8_bom_is_accepted():
    assert len(parse_csv("\ufeffname,email\nA,a@example.com\n".encode("utf-8"))) == 1


def test_too_many_rows_is_rejected():
    data = "name,email\n" + "".join(f"n{i},e{i}@example.com\n" for i in range(MAX_ROWS + 1))
    with pytest.raises(AuthError):
        parse_csv(data.encode())

def test_import_mapping_preserves_campaign_external_id_and_requirement():
    from app.modules.leads.csv_import import _to_lead

    body = _to_lead({
        "name": "Rahim Uddin",
        "email": "rahim@example.com",
        "phone": "",
        "company_name": "ABC Traders",
        "source_campaign": "Eid Offer 2026",
        "external_id": "EXT-1001",
        "consent": "yes",
        "requirement": "Needs CRM for 20-person sales team",
    })

    assert body.source == "csv"
    assert body.source_campaign == "Eid Offer 2026"
    assert body.external_id == "EXT-1001"
    assert body.consent is True
    assert body.notes == "Requirement: Needs CRM for 20-person sales team"


def test_import_mapping_accepts_false_consent():
    from app.modules.leads.csv_import import _to_lead

    body = _to_lead({
        "name": "Karim",
        "email": "karim@example.com",
        "consent": "no",
    })

    assert body.consent is False


def test_import_mapping_rejects_unknown_consent():
    from app.modules.leads.csv_import import _to_lead

    with pytest.raises(AuthError) as exc:
        _to_lead({
            "name": "Karim",
            "email": "karim@example.com",
            "consent": "maybe",
        })

    assert exc.value.code == "invalid_consent"


def test_parse_rejects_duplicate_headers():
    with pytest.raises(AuthError):
        parse_csv(b"name,email, email\nA,a@example.com,b@example.com\n")
