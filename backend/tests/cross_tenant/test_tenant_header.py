import pytest

from tests.cross_tenant.support import OTHER

ROLES = [("admin", "admin"), ("manager", "manager"), ("rep", "rep"), ("rep2", "rep")]
KEYS = [key for key, _ in ROLES]
LETTERS = ["a", "b"]


def _headers(tokens, seed, letter, key, tenant_letter):
    return {**tokens[(letter, key)], "X-Tenant-ID": str(seed.get(tenant_letter).id)}


@pytest.mark.parametrize("letter", LETTERS)
@pytest.mark.parametrize(("key", "role"), ROLES)
def test_member_can_use_own_company(admin_client, seed, tokens, letter, key, role):
    r = admin_client.get("/_ctx", headers=_headers(tokens, seed, letter, key, letter))
    assert r.status_code == 200, r.text
    assert r.json() == {"tenant_id": str(seed.get(letter).id), "role": role}


@pytest.mark.parametrize("letter", LETTERS)
@pytest.mark.parametrize("key", KEYS)
def test_member_cannot_use_the_other_company(admin_client, seed, tokens, letter, key):
    other = OTHER[letter]
    r = admin_client.get("/_ctx", headers=_headers(tokens, seed, letter, key, other))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    assert seed.get(other).name not in r.text  # no details about the other company leak


@pytest.mark.parametrize("letter", LETTERS)
def test_deactivated_membership_is_forbidden(admin_client, seed, tokens, letter):
    r = admin_client.get("/_ctx", headers=_headers(tokens, seed, letter, "ex_rep", letter))
    assert r.status_code == 403


def test_unknown_company_is_forbidden(admin_client, tokens):
    headers = {**tokens[("a", "admin")], "X-Tenant-ID": "11111111-1111-4111-8111-111111111111"}
    assert admin_client.get("/_ctx", headers=headers).status_code == 403


def test_missing_tenant_header_is_bad_request(admin_client, tokens):
    assert admin_client.get("/_ctx", headers=tokens[("a", "admin")]).status_code == 400


def test_missing_token_is_unauthorized(admin_client, seed):
    r = admin_client.get("/_ctx", headers={"X-Tenant-ID": str(seed.a.id)})
    assert r.status_code == 401


def test_tenant_id_in_the_url_is_never_used(admin_client, seed, tokens):
    # Only the verified header counts. A tenant_id in the query string is ignored.
    url = f"/_ctx?tenant_id={seed.b.id}"
    own = admin_client.get(url, headers=_headers(tokens, seed, "a", "admin", "a"))
    assert own.json()["tenant_id"] == str(seed.a.id)
    assert admin_client.get(url, headers=tokens[("a", "admin")]).status_code == 400
