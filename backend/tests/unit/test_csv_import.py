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
