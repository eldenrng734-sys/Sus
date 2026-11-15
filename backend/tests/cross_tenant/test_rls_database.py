import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.cross_tenant.support import read_dotenv, rls_pending, set_tenant

# refresh_tokens and lead_forms resolve before tenant context exists (public endpoints)
SPECIAL_TABLES = {"refresh_tokens", "lead_forms"}

TENANT_TABLES_SQL = """
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
WHERE n.nspname = 'public' AND c.relkind = 'r'
"""


def _visible_leads(engine, tenant_id=None) -> set[str]:
    with engine.begin() as conn:
        if tenant_id is not None:
            set_tenant(conn, tenant_id)
        return {str(row[0]) for row in conn.execute(text("SELECT id FROM leads"))}


def test_every_tenant_table_has_forced_rls_and_a_tenant_policy(admin_engine):
    with admin_engine.connect() as conn:
        tables = [
            (name, enabled, forced)
            for name, enabled, forced in conn.execute(text(TENANT_TABLES_SQL))
            if name not in SPECIAL_TABLES
        ]
        policies: dict[str, list[str]] = {}
        rows = conn.execute(
            text("SELECT tablename, qual FROM pg_policies WHERE schemaname = 'public'")
        )
        for table, qual in rows:
            policies.setdefault(table, []).append(qual or "")
    no_rls = [name for name, enabled, forced in tables if not (enabled and forced)]
    no_policy = [
        name
        for name, _, _ in tables
        if not any("app.tenant_id" in q for q in policies.get(name, []))
    ]
    assert not no_rls, f"RLS not enabled+forced on: {no_rls}"
    assert not no_policy, f"No app.tenant_id policy on: {no_policy}"


def test_crm_app_role_cannot_bypass_rls(admin_engine):
    with admin_engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crm_app'")
        ).one_or_none()
    assert row is not None, "role crm_app does not exist yet"
    assert row.rolsuper is False
    assert row.rolbypassrls is False


@rls_pending
def test_configured_app_user_is_not_a_superuser(admin_engine):
    database_url = read_dotenv().get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not found in the root .env")
    user = make_url(database_url).username
    with admin_engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :u"), {"u": user}
        ).one()
    assert row.rolsuper is False and row.rolbypassrls is False, (
        f"The app connects as '{user}', which bypasses RLS. Split to crm_app before Day 3 ends."
    )


@rls_pending
def test_no_tenant_context_sees_no_rows(app_engine, seed):
    assert _visible_leads(app_engine) == set()


@rls_pending
def test_each_company_sees_only_its_own_leads(app_engine, seed):
    for company in (seed.a, seed.b):
        assert _visible_leads(app_engine, company.id) == {str(i) for i in company.lead_ids}


@rls_pending
def test_cannot_update_or_delete_another_companys_rows(app_engine, admin_engine, seed):
    victim = seed.b.lead_ids[0]
    with app_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        updated = conn.execute(
            text("UPDATE leads SET name = 'hacked' WHERE id = :i"), {"i": victim}
        )
        deleted = conn.execute(text("DELETE FROM leads WHERE id = :i"), {"i": victim})
        assert updated.rowcount == 0
        assert deleted.rowcount == 0
    with admin_engine.connect() as conn:
        name = conn.scalar(text("SELECT name FROM leads WHERE id = :i"), {"i": victim})
    assert name is not None and name != "hacked"


@rls_pending
def test_cannot_insert_a_row_for_another_company(app_engine, seed):
    with pytest.raises(DBAPIError):
        with app_engine.begin() as conn:
            set_tenant(conn, seed.a.id)
            conn.execute(
                text(
                    "INSERT INTO leads (tenant_id, name, email, source) "
                    "VALUES (:t, 'X', 'rls-insert@example.com', 'manual')"
                ),
                {"t": seed.b.id},
            )


@rls_pending
def test_api_returns_only_the_callers_company(make_client, app_engine, tokens, seed):
    client = make_client(app_engine)
    for letter in ("a", "b"):
        company = seed.get(letter)
        headers = {**tokens[(letter, "admin")], "X-Tenant-ID": str(company.id)}
        r = client.get("/_leads", headers=headers)
        assert r.status_code == 200, r.text
        assert set(r.json()["ids"]) == {str(i) for i in company.lead_ids}
