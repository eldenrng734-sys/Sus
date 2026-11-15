import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.modules.lead_forms.router import router
from tests.cross_tenant.support import Seed, set_tenant


@pytest.fixture
def public_form_client(app_engine: Engine) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)

    def _session() -> Iterator[Session]:
        with Session(app_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as client:
        yield client


def test_form_tenant_is_resolved_from_public_id_not_request_header(
    admin_engine: Engine,
    seed: Seed,
    public_form_client: TestClient,
) -> None:
    with admin_engine.connect() as conn:
        exists = conn.scalar(text("SELECT to_regclass('public.lead_forms')"))
    if exists is None:
        pytest.skip("lead_forms migration has not been applied")

    public_id = f"pf_test_{uuid.uuid4().hex}"
    email = f"form-{uuid.uuid4().hex}@example.test"
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        conn.execute(
            text(
                "INSERT INTO lead_forms "
                "(tenant_id, public_id, name, allowed_fields, consent_text, is_active) "
                "VALUES (:tenant_id, :public_id, 'Test form', CAST(:fields AS jsonb), "
                "'I agree to be contacted.', true)"
            ),
            {
                "tenant_id": seed.a.id,
                "public_id": public_id,
                "fields": json.dumps(["name", "email"]),
            },
        )

    response = public_form_client.post(
        f"/api/v1/public/forms/{public_id}/submit",
        headers={"X-Tenant-ID": str(seed.b.id)},
        json={
            "name": "Public Form Lead",
            "email": email,
            "consent": True,
            "consent_version": "v1",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "received"

    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        lead_tenant = conn.scalar(
            text("SELECT tenant_id FROM leads WHERE email = :email"),
            {"email": email},
        )
    assert str(lead_tenant) == str(seed.a.id)
