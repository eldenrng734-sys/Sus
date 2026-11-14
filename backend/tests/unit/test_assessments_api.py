import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.tenancy import get_tenant_context
from app.database.session import get_session
from app.main import app


class FakeSession:
    def __init__(self, assessment=None):
        self.assessment = assessment
        self.statement = None
        self.committed = False

    def scalars(self, statement):
        self.statement = statement
        return SimpleNamespace(all=lambda: [self.assessment] if self.assessment else [])

    def scalar(self, statement):
        self.statement = statement
        return self.assessment

    def commit(self):
        self.committed = True


def make_assessment(tenant_id=None, **overrides):
    values = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "lead_id": uuid.uuid4(),
        "conversation_id": None,
        "category": "unknown",
        "intent": "request_demo",
        "interest": None,
        "buying_stage": "consideration",
        "sentiment": "positive",
        "priority": "medium",
        "lead_score": 65,
        "recommended_action": "schedule_demo",
        "follow_up_days": 2,
        "confidence": 0.9,
        "needs_human_review": True,
        "review_status": "pending",
        "reviewed_by_user_id": None,
        "reviewed_at": None,
        "review_note": None,
        "summary": "Customer requested a demo.",
        "model": "test-model",
        "prompt_version": "test-prompt",
        "status": "ok",
        "created_at": datetime.now(UTC),
        "raw_output": {"private": "do not return"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_context(role="admin"):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=role,
        team_id=uuid.uuid4() if role == "manager" else None,
    )


@pytest.fixture
def api_client():
    original_overrides = app.dependency_overrides.copy()
    session = FakeSession()
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def authenticate(context):
    app.dependency_overrides[get_tenant_context] = lambda: context


def test_list_assessments_and_review_filters(api_client):
    client, session = api_client
    context = make_context()
    assessment = make_assessment(tenant_id=context.tenant_id)
    session.assessment = assessment
    authenticate(context)

    response = client.get(
        "/api/v1/assessments",
        params={"needs_human_review": "true", "review_status": "pending", "limit": 10, "offset": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"] == {"limit": 10, "offset": 5}
    assert payload["data"][0]["id"] == str(assessment.id)
    assert "raw_output" not in payload["data"][0]
    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert compiled.params["tenant_id_1"] == context.tenant_id
    assert any(value == "pending" for value in compiled.params.values())
    assert "lead_assessments.needs_human_review" in str(compiled)
    assert "true" in str(compiled).lower()


def test_rep_assessment_queries_are_limited_to_assigned_leads(api_client):
    client, session = api_client
    context = make_context(role="rep")
    session.assessment = make_assessment(tenant_id=context.tenant_id)
    authenticate(context)

    response = client.get("/api/v1/assessments")

    assert response.status_code == 200
    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert "leads.assigned_user_id" in str(compiled)
    assert context.user_id in compiled.params.values()


def test_get_assessment_details(api_client):
    client, session = api_client
    context = make_context()
    assessment = make_assessment(tenant_id=context.tenant_id)
    session.assessment = assessment
    authenticate(context)

    response = client.get(f"/api/v1/assessments/{assessment.id}")

    assert response.status_code == 200
    assert response.json()["data"]["summary"] == assessment.summary
    assert "raw_output" not in response.json()["data"]
    assert (
        context.tenant_id in session.statement.compile(dialect=postgresql.dialect()).params.values()
    )


@pytest.mark.parametrize("review_status", ["approved", "rejected"])
def test_review_assessment_sets_authenticated_reviewer_and_time(api_client, review_status):
    client, session = api_client
    context = make_context()
    assessment = make_assessment(tenant_id=context.tenant_id)
    session.assessment = assessment
    authenticate(context)

    response = client.patch(
        f"/api/v1/assessments/{assessment.id}/review",
        json={"review_status": review_status, "review_note": "  Reviewed by manager  "},
    )

    assert response.status_code == 200
    assert assessment.review_status == review_status
    assert assessment.reviewed_by_user_id == context.user_id
    assert assessment.reviewed_at.tzinfo is not None
    assert assessment.review_note == "Reviewed by manager"
    assert response.json()["data"]["reviewed_by_user_id"] == str(context.user_id)
    assert session.committed is True


def test_cross_tenant_assessment_is_not_found(api_client):
    client, session = api_client
    context = make_context()
    authenticate(context)
    session.assessment = None

    response = client.get(f"/api/v1/assessments/{uuid.uuid4()}")

    assert response.status_code == 404
    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert context.tenant_id in compiled.params.values()


def test_review_rejects_non_pending_assessment(api_client):
    client, session = api_client
    context = make_context()
    session.assessment = make_assessment(
        tenant_id=context.tenant_id,
        review_status="approved",
        needs_human_review=True,
    )
    authenticate(context)

    response = client.patch(
        f"/api/v1/assessments/{session.assessment.id}/review",
        json={"review_status": "rejected"},
    )

    assert response.status_code == 409
    assert session.committed is False


def test_representative_cannot_review_assessment(api_client):
    client, session = api_client
    context = make_context(role="rep")
    session.assessment = make_assessment(tenant_id=context.tenant_id)
    authenticate(context)

    response = client.patch(
        f"/api/v1/assessments/{session.assessment.id}/review",
        json={"review_status": "approved"},
    )

    assert response.status_code == 403
    assert session.committed is False


def test_invalid_review_status_is_rejected(api_client):
    client, _ = api_client
    context = make_context()
    authenticate(context)

    response = client.patch(
        f"/api/v1/assessments/{uuid.uuid4()}/review",
        json={"review_status": "not_a_status"},
    )

    assert response.status_code == 422


def test_review_does_not_accept_reviewer_identity_from_request(api_client):
    client, session = api_client
    context = make_context()
    session.assessment = make_assessment(tenant_id=context.tenant_id)
    authenticate(context)

    response = client.patch(
        f"/api/v1/assessments/{session.assessment.id}/review",
        json={
            "review_status": "approved",
            "reviewed_by_user_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 422
    assert session.assessment.reviewed_by_user_id is None
    assert session.committed is False


def test_assessments_endpoints_reject_unauthenticated_access(api_client):
    client, _ = api_client
    app.dependency_overrides.pop(get_tenant_context, None)

    response = client.get("/api/v1/assessments")

    assert response.status_code == 401
