import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Message
from app.modules.messaging import service as messaging_service
from app.modules.messaging.router import router as messaging_router
from tests.cross_tenant.support import Seed, set_tenant

PHONE_NUMBER_ID = "wa-outbound-test"
MESSAGES_PATH = rf"^/v\d+\.\d+/{PHONE_NUMBER_ID}/messages$"


@pytest.fixture(scope="module")
def api_client(admin_engine: Engine) -> Iterator[TestClient]:
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)
    mini.include_router(messaging_router)

    def _session() -> Iterator[Session]:
        with Session(admin_engine) as session:
            yield session

    mini.dependency_overrides[get_session] = _session
    with TestClient(mini, client=("127.0.0.1", 50000)) as client:
        yield client


@pytest.fixture(autouse=True)
def fake_whatsapp_credentials(monkeypatch):
    monkeypatch.setattr(
        messaging_service,
        "get_credentials",
        lambda *_args, **_kwargs: {
            "access_token": "test-token",
            "phone_number_id": PHONE_NUMBER_ID,
        },
    )


@pytest.fixture
def meta_route():
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        # Real provider IDs are unique; reusing one would hit the tenant-wide
        # (tenant_id, provider, provider_message_id) unique index.
        route = mock.post(path__regex=MESSAGES_PATH).mock(
            side_effect=lambda request: httpx.Response(
                200,
                json={"messages": [{"id": f"wamid.{uuid.uuid4().hex}"}]},
            )
        )
        yield route


def _headers(tokens, seed: Seed, letter: str, role_key: str) -> dict[str, str]:
    return {
        **tokens[(letter, role_key)],
        "X-Tenant-ID": str(seed.get(letter).id),
    }


def _create_lead(
    admin_engine: Engine,
    seed: Seed,
    *,
    assigned_to: str = "rep",
    opted_out: bool = False,
) -> uuid.UUID:
    tenant = seed.a
    lead_id = uuid.uuid4()
    phone = f"+88017{uuid.uuid4().int % 100_000_000:08d}"
    with admin_engine.begin() as conn:
        set_tenant(conn, tenant.id)
        conn.execute(
            text(
                "INSERT INTO leads "
                "(id, tenant_id, name, email, phone, source, assigned_user_id, team_id, "
                "consent, opted_out, opted_out_at) "
                "VALUES (:id, :tenant, :name, :email, :phone, 'manual', :assignee, :team, "
                "true, :opted_out, :opted_out_at)"
            ),
            {
                "id": lead_id,
                "tenant": tenant.id,
                "name": "Outbound Test Lead",
                "email": f"outbound-{lead_id}@example.test",
                "phone": phone,
                "assignee": tenant.users[assigned_to][0],
                "team": tenant.team_id,
                "opted_out": opted_out,
                "opted_out_at": datetime.now(UTC) if opted_out else None,
            },
        )
    return lead_id


def _create_conversation(
    admin_engine: Engine,
    seed: Seed,
    lead_id: uuid.UUID,
    *,
    last_inbound_at: datetime | None,
) -> uuid.UUID:
    conversation_id = uuid.uuid4()
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        conn.execute(
            text(
                "INSERT INTO conversations "
                "(id, tenant_id, lead_id, channel, external_conversation_id, "
                "external_contact_id, status, last_inbound_at, last_message_at) "
                "VALUES (:id, :tenant, :lead, 'whatsapp', :external, :contact, 'open', "
                ":inbound, :inbound)"
            ),
            {
                "id": conversation_id,
                "tenant": seed.a.id,
                "lead": lead_id,
                "external": f"conv-{conversation_id}",
                "contact": f"contact-{conversation_id}",
                "inbound": last_inbound_at,
            },
        )
    return conversation_id


def _message_count(admin_engine: Engine, seed: Seed, conversation_id: uuid.UUID) -> int:
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        return (
            session.query(Message)
            .filter(
                Message.tenant_id == seed.a.id,
                Message.conversation_id == conversation_id,
            )
            .count()
        )


def _reload_message(admin_engine: Engine, seed: Seed, message_id: uuid.UUID) -> Message:
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        message = session.get(Message, message_id)
        assert message is not None
        session.refresh(message)
        return message


def test_in_window_text_is_sent(api_client, admin_engine, seed, tokens, meta_route):
    lead_id = _create_lead(admin_engine, seed)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )

    response = api_client.post(
        "/api/v1/messages",
        headers=_headers(tokens, seed, "a", "rep"),
        json={"conversation_id": str(conversation_id), "text": "Thanks, Tuesday works."},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "sent"
    assert data["provider_message_id"].startswith("wamid.")

    stored = _reload_message(admin_engine, seed, uuid.UUID(data["id"]))
    assert stored.status == "sent"
    assert stored.provider_message_id == data["provider_message_id"]
    assert stored.direction == "outbound"

    body = json.loads(meta_route.calls[0].request.content)
    assert body["type"] == "text"
    assert body["text"] == {"body": "Thanks, Tuesday works."}


def test_out_of_window_without_template_is_rejected(
    api_client, admin_engine, seed, tokens, meta_route
):
    lead_id = _create_lead(admin_engine, seed)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC) - timedelta(hours=25),
    )

    response = api_client.post(
        "/api/v1/messages",
        headers=_headers(tokens, seed, "a", "rep"),
        json={"conversation_id": str(conversation_id), "text": "Are you still interested?"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "window_closed"
    assert meta_route.call_count == 0
    assert _message_count(admin_engine, seed, conversation_id) == 0


def test_out_of_window_template_is_allowed(api_client, admin_engine, seed, tokens, meta_route):
    lead_id = _create_lead(admin_engine, seed)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC) - timedelta(days=7),
    )

    response = api_client.post(
        "/api/v1/messages",
        headers=_headers(tokens, seed, "a", "rep"),
        json={
            "conversation_id": str(conversation_id),
            "template": {
                "name": "demo_follow_up",
                "language": "en_US",
                "params": ["Ayesha", "Tuesday 3 PM"],
            },
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "sent"

    body = json.loads(meta_route.calls[0].request.content)
    assert body["type"] == "template"
    assert body["template"]["name"] == "demo_follow_up"
    assert body["template"]["language"] == {"code": "en_US"}
    assert body["template"]["components"][0]["parameters"][0] == {
        "type": "text",
        "text": "Ayesha",
    }


def test_send_template_is_usable_without_the_http_route(admin_engine, seed, meta_route):
    """Workflow B calls the service directly with a tenant-scoped session."""
    lead_id = _create_lead(admin_engine, seed)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC) - timedelta(days=7),
    )

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        message = asyncio.run(
            messaging_service.send_template(
                conversation_id,
                "demo_follow_up",
                "en_US",
                ["Ayesha"],
                session,
            )
        )

    assert message.status == "sent"
    assert message.provider_message_id is not None
    assert meta_route.call_count == 1


def test_opted_out_lead_is_rejected(api_client, admin_engine, seed, tokens, meta_route):
    lead_id = _create_lead(admin_engine, seed, opted_out=True)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )

    response = api_client.post(
        "/api/v1/messages",
        headers=_headers(tokens, seed, "a", "rep"),
        json={"conversation_id": str(conversation_id), "text": "Hello again"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "opted_out"
    assert meta_route.call_count == 0
    assert _message_count(admin_engine, seed, conversation_id) == 0


def test_rep_cannot_send_on_another_reps_lead(api_client, admin_engine, seed, tokens, meta_route):
    lead_id = _create_lead(admin_engine, seed, assigned_to="rep2")
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )

    response = api_client.post(
        "/api/v1/messages",
        headers=_headers(tokens, seed, "a", "rep"),
        json={"conversation_id": str(conversation_id), "text": "Not my lead"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert meta_route.call_count == 0
    assert _message_count(admin_engine, seed, conversation_id) == 0


def test_provider_500_is_retried_then_message_failed(
    api_client,
    admin_engine,
    seed,
    tokens,
    meta_route,
    monkeypatch,
):
    monkeypatch.setattr(settings, "meta_send_backoff_seconds", 0.0)
    meta_route.mock(
        return_value=httpx.Response(500, json={"error": {"code": 2, "message": "down"}})
    )

    lead_id = _create_lead(admin_engine, seed)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )

    response = api_client.post(
        "/api/v1/messages",
        headers=_headers(tokens, seed, "a", "rep"),
        json={"conversation_id": str(conversation_id), "text": "Retry me"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"
    assert meta_route.call_count == settings.meta_send_max_attempts

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        message = session.query(Message).filter(Message.conversation_id == conversation_id).one()
        assert message.status == "failed"
        assert message.error_code is not None
        assert message.error_code.startswith("provider_500")


def test_same_idempotency_key_returns_one_message(
    api_client, admin_engine, seed, tokens, meta_route
):
    lead_id = _create_lead(admin_engine, seed)
    conversation_id = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )
    headers = {
        **_headers(tokens, seed, "a", "rep"),
        "Idempotency-Key": f"send-{uuid.uuid4()}",
    }
    body = {"conversation_id": str(conversation_id), "text": "Send exactly once"}

    first = api_client.post("/api/v1/messages", headers=headers, json=body)
    second = api_client.post("/api/v1/messages", headers=headers, json=body)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.headers["Idempotent-Replay"] == "true"
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert meta_route.call_count == 1
    assert _message_count(admin_engine, seed, conversation_id) == 1


def test_same_key_on_a_different_conversation_is_rejected(
    api_client, admin_engine, seed, tokens, meta_route
):
    lead_id = _create_lead(admin_engine, seed)
    first_conversation = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )
    second_conversation = _create_conversation(
        admin_engine,
        seed,
        lead_id,
        last_inbound_at=datetime.now(UTC),
    )
    headers = {
        **_headers(tokens, seed, "a", "rep"),
        "Idempotency-Key": f"send-{uuid.uuid4()}",
    }

    first = api_client.post(
        "/api/v1/messages",
        headers=headers,
        json={"conversation_id": str(first_conversation), "text": "First"},
    )
    second = api_client.post(
        "/api/v1/messages",
        headers=headers,
        json={"conversation_id": str(second_conversation), "text": "Second"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_conflict"
    assert meta_route.call_count == 1
