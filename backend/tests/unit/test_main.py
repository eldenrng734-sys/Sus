import asyncio
import json
import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.permissions import require_any_member
from app.database.session import get_session
from app.main import app, auth_error_handler
from app.modules.auth.errors import AuthError


def test_auth_routers_and_day4_lead_routes_are_registered():
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/password-reset" in paths
    assert "/api/v1/conversations" in paths
    assert "/api/v1/leads" in paths
    assert "/api/v1/leads/{lead_id}" in paths
    assert "/api/v1/leads/{lead_id}/assign" in paths
    assert "/api/v1/leads/{lead_id}/notes" in paths
    assert "/api/v1/leads/{lead_id}/timeline" in paths
    assert "/health" in paths


def test_create_lead_requires_idempotency_key_header():
    schema = app.openapi()
    parameters = schema["paths"]["/api/v1/leads"]["post"]["parameters"]
    key_header = next(p for p in parameters if p["name"] == "Idempotency-Key")

    assert key_header["in"] == "header"
    assert key_header["required"] is True
    assert key_header["schema"]["minLength"] == 8
    assert key_header["schema"]["maxLength"] == 128


def test_lead_list_exposes_documented_filters():
    schema = app.openapi()
    parameters = schema["paths"]["/api/v1/leads"]["get"]["parameters"]
    names = {parameter["name"] for parameter in parameters}

    assert {
        "q",
        "status",
        "source",
        "priority",
        "assigned_user_id",
        "team_id",
        "created_from",
        "created_to",
        "sort",
        "limit",
        "cursor",
    } <= names


def test_lead_patch_requires_optimistic_version():
    schema = app.openapi()
    body_schema = schema["paths"]["/api/v1/leads/{lead_id}"]["patch"]["requestBody"]
    schema_ref = body_schema["content"]["application/json"]["schema"]["$ref"]
    schema_name = schema_ref.rsplit("/", 1)[-1]

    assert "version" in schema["components"]["schemas"][schema_name]["required"]


def test_auth_error_handler_preserves_structured_details():
    request = MagicMock()
    request.state.request_id = str(uuid.uuid4())
    error = AuthError(
        409,
        "duplicate_lead",
        "Duplicate lead",
        details=[{"existing_lead_id": str(uuid.uuid4())}],
    )

    response = asyncio.run(auth_error_handler(request, error))
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["error"]["details"] == error.details

def test_lead_list_rejects_unknown_query_filters():
    app.dependency_overrides[require_any_member] = lambda: MagicMock(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="admin",
        team_id=None,
    )
    app.dependency_overrides[get_session] = lambda: MagicMock()
    try:
        response = TestClient(app).get("/api/v1/leads?not_a_filter=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
