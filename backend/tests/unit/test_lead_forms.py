import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.session import get_session
from app.modules.lead_forms import service
from app.modules.lead_forms.router import MAX_REQUEST_BODY_BYTES, router
from app.modules.leads.capture import CaptureError


class FakeSession:
    def __init__(self, form) -> None:
        self.form = form
        self.scalar_calls = 0
        self.execute_calls = []
        self.commit_calls = 0
        self.content_lengths = []

    def execute(self, statement, params=None):
        self.execute_calls.append((str(statement), params))
        return None

    def scalar(self, statement):
        self.scalar_calls += 1
        return self.form

    def commit(self):
        self.commit_calls += 1


def make_client(monkeypatch, form=None):
    session = FakeSession(form)
    app = FastAPI()
    app.include_router(router)

    @app.middleware("http")
    async def record_content_length(request, call_next):
        session.content_lengths.append(request.headers.get("content-length"))
        return await call_next(request)

    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    captured = []

    def capture_lead(db, *, tenant_id, data, actor_user_id=None):
        if not data.email and not data.phone:
            raise CaptureError("email or phone is required")
        captured.append((tenant_id, data))
        return SimpleNamespace(lead=SimpleNamespace(id=uuid.uuid4()), created=True)

    monkeypatch.setattr(service, "capture_lead", capture_lead)
    return TestClient(app), session, captured


def form(allowed_fields=None):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        public_id="opaque-form-reference",
        allowed_fields=(
            ["name", "email", "phone", "company_name", "message", "utm"]
            if allowed_fields is None
            else allowed_fields
        ),
        consent_text="I agree to be contacted.",
        is_active=True,
    )


def submission(**overrides):
    data = {
        "name": "  Ada Lovelace  ",
        "email": "  ADA@Example.com ",
        "phone": None,
        "company_name": " Analytical Engines ",
        "message": " Please call ",
        "consent": True,
        "consent_version": "v1",
        "utm": {"source": " newsletter ", "medium": "email", "campaign": "launch"},
    }
    data.update(overrides)
    return data


def test_submission_returns_201_and_sanitizes_fields(monkeypatch):
    client, session, captured = make_client(monkeypatch, form())

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(),
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert "id" in payload
    assert "status" not in payload
    assert "reference" not in payload
    assert "lead_id" not in payload
    assert "tenant_id" not in payload
    assert len(captured) == 1
    tenant_id, data = captured[0]
    assert tenant_id == session.form.tenant_id
    assert data.name == "Ada Lovelace"
    assert data.email == "ada@example.com"
    assert data.source == "website_form"
    assert data.consent_source == "web_form"
    assert data.interaction_metadata["consent_text"] == "I agree to be contacted."
    assert data.interaction_metadata["consent_version"] == "v1"
    assert data.interaction_metadata["utm"]["source"] == "newsletter"
    assert session.commit_calls == 1
    assert any(
        "set_config('app.public_form_id', '', true)" in statement
        for statement, _ in session.execute_calls
    )


def test_255_character_campaign_is_preserved_in_metadata_and_truncated_for_capture(
    monkeypatch,
):
    campaign = "c" * 255
    client, _, captured = make_client(monkeypatch, form())

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(utm={"campaign": campaign}),
    )

    assert response.status_code == 201
    assert len(captured[0][1].source_campaign) == 200
    assert captured[0][1].interaction_metadata["utm"]["campaign"] == campaign


def test_utm_term_and_content_are_passed_through(monkeypatch):
    client, _, captured = make_client(monkeypatch, form())

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(utm={"term": "bangladesh", "content": "hero_banner"}),
    )

    assert response.status_code == 201
    assert captured[0][1].interaction_metadata["utm"]["term"] == "bangladesh"
    assert captured[0][1].interaction_metadata["utm"]["content"] == "hero_banner"


def test_consent_version_is_optional(monkeypatch):
    client, _, captured = make_client(monkeypatch, form())

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(consent_version=None),
    )

    assert response.status_code == 201
    assert captured[0][1].interaction_metadata["consent_version"] is None


def test_honeypot_submission_returns_success_without_capture(monkeypatch):
    client, session, captured = make_client(monkeypatch, form())

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(_hp="bot"),
    )

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "received"
    assert captured == []
    assert session.commit_calls == 0


def test_disallowed_fields_are_ignored(monkeypatch):
    client, _, captured = make_client(monkeypatch, form(["name", "phone"]))

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(email="ignored@example.com", company_name="Ignored", message="Ignored"),
    )

    assert response.status_code == 422
    assert captured == []


def test_unknown_form_returns_404(monkeypatch):
    client, session, captured = make_client(monkeypatch, None)

    response = client.post(
        "/api/v1/public/forms/unknown/submit",
        json=submission(),
    )

    assert response.status_code == 404
    assert session.scalar_calls == 1
    assert captured == []


def test_oversized_content_length_is_rejected_before_database_access(monkeypatch):
    client, session, captured = make_client(monkeypatch, form())
    raw_body = json.dumps(submission()).encode() + b" " * MAX_REQUEST_BODY_BYTES

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        content=raw_body,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert session.content_lengths == [str(len(raw_body))]
    assert session.scalar_calls == 0
    assert session.execute_calls == []
    assert captured == []
    assert "opaque-form-reference" not in response.text


def test_oversized_stream_without_content_length_is_rejected(monkeypatch):
    client, session, captured = make_client(monkeypatch, form())
    body = json.dumps(submission()).encode() + b" " * MAX_REQUEST_BODY_BYTES

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        content=iter([body]),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert session.content_lengths == [None]
    assert session.scalar_calls == 0
    assert session.execute_calls == []
    assert captured == []


def test_false_consent_is_rejected_before_database_access(monkeypatch):
    client, session, captured = make_client(monkeypatch, form())

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(consent=False),
    )

    assert response.status_code == 422
    assert session.scalar_calls == 0
    assert captured == []


@pytest.mark.parametrize("allowed_fields", [[], ["name"], ["name", "utm"]])
def test_missing_contact_fields_are_rejected(monkeypatch, allowed_fields):
    client, _, captured = make_client(monkeypatch, form(allowed_fields))

    response = client.post(
        "/api/v1/public/forms/opaque-form-reference/submit",
        json=submission(),
    )

    assert response.status_code == 422
    assert captured == []
