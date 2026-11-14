import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.leads.router import router as leads_router
from tests.cross_tenant.support import set_tenant


@pytest.fixture(scope="module")
def csv_client(admin_engine):
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)
    mini.include_router(leads_router)

    def _session():
        with Session(admin_engine) as session:
            yield session

    mini.dependency_overrides[get_session] = _session
    return TestClient(mini, client=("127.0.0.1", 50000))


def _headers(tokens, seed, key, tag):
    return {
        **tokens[("a", key)],
        "X-Tenant-ID": str(seed.a.id),
        "Idempotency-Key": f"import-{tag}-0001",
    }


def test_import_reports_created_duplicates_and_errors(csv_client, admin_engine, seed, tokens):
    tag = uuid.uuid4().hex[:8]
    body = (
        "name,email,phone\n"
        f"Ayesha,ayesha-{tag}@example.com,\n"
        f"Rahim,rahim-{tag}@example.com,\n"
        f"Ayesha Again,ayesha-{tag}@example.com,\n"
        f",nobody-{tag}@example.com,\n"
        f"=Evil,evil-{tag}@example.com,\n"
    )
    r = csv_client.post(
        "/api/v1/leads/import",
        headers=_headers(tokens, seed, "manager", tag),
        files={"file": ("leads.csv", body, "text/csv")},
        data={"dry_run": "false"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    print("\nCSV IMPORT RESULT:", data)
    assert data["total_rows"] == 5
    assert data["created_count"] == 3
    assert data["duplicate_count"] == 1
    assert data["error_count"] == 1
    assert {e["row"] for e in data["errors"]} == {4, 5}

    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        name = conn.scalar(
            text("SELECT name FROM leads WHERE email = :e"), {"e": f"evil-{tag}@example.com"}
        )
    assert name == "'=Evil"


def test_dry_run_writes_nothing(csv_client, admin_engine, seed, tokens):
    tag = uuid.uuid4().hex[:8]
    body = f"name,email\nDry Run,dry-{tag}@example.com\n"
    r = csv_client.post(
        "/api/v1/leads/import",
        headers=_headers(tokens, seed, "manager", tag),
        files={"file": ("leads.csv", body, "text/csv")},
        data={"dry_run": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created_count"] == 1
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        count = conn.scalar(
            text("SELECT count(*) FROM leads WHERE email = :e"), {"e": f"dry-{tag}@example.com"}
        )
    assert count == 0


def test_rep_cannot_import(csv_client, seed, tokens):
    tag = uuid.uuid4().hex[:8]
    r = csv_client.post(
        "/api/v1/leads/import",
        headers=_headers(tokens, seed, "rep", tag),
        files={"file": ("leads.csv", "name,email\nX,x@example.com\n", "text/csv")},
    )
    assert r.status_code == 403
