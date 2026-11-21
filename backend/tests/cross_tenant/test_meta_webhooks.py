"""Meta Lead Ads and Messenger webhook tests against real PostgreSQL.

The webhook must return 200 quickly. Lead Ad details are fetched in the
after-commit background job, so these tests also prove that path end to end.
"""

import hashlib
import hmac
import json
import os
import uuid
from collections.abc import Iterator

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_session, set_tenant_context
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation, Message
from app.modules.integrations.crypto import encrypt_credentials, register_key
from app.modules.integrations.models import Integration
from app.modules.integrations.webhook_router import router as webhook_router
from app.modules.leads.models import Interaction, Lead
from tests.cross_tenant.support import Seed, set_tenant

SECRET = "meta-test-secret"
VERIFY_TOKEN = "meta-verify-token"
URL = "/api/v1/webhooks/meta"


@pytest.fixture(scope="module", autouse=True)
def _secrets() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "meta_app_secret", SecretStr(SECRET))
        patch.setattr(settings, "webhook_verify_token", SecretStr(VERIFY_TOKEN))
        yield


@pytest.fixture(scope="module", autouse=True)
def _encryption_key() -> None:
    register_key(1, os.urandom(32))


@pytest.fixture(scope="module")
def hook_client(admin_engine: Engine) -> Iterator[TestClient]:
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)
    mini.include_router(webhook_router)

    def _session() -> Iterator[Session]:
        with Session(admin_engine) as session:
            yield session

    mini.dependency_overrides[get_session] = _session
    with TestClient(mini, client=("127.0.0.1", 50000)) as client:
        yield client


def _page_id() -> str:
    return str(uuid.uuid4().int)[:15]


def _create_meta_integration(
    admin_engine: Engine,
    tenant_id: uuid.UUID,
    *,
    access_token: str = "page-access-token",
) -> str:
    page_id = _page_id()
    with Session(admin_engine) as session:
        set_tenant_context(session, str(tenant_id))
        integration = Integration(
            tenant_id=tenant_id,
            provider="meta",
            provider_account_id=page_id,
            status="active",
            scopes=["leads_retrieval", "ads_management", "pages_manage_metadata"],
        )
        session.add(integration)
        session.flush()
        integration.credentials_encrypted = encrypt_credentials(
            {
                "access_token": access_token,
                "provider_account_id": page_id,
            },
            tenant_id,
            integration.id,
        )
        session.commit()
    return page_id


@pytest.fixture()
def meta_account(admin_engine: Engine, seed: Seed) -> str:
    return _create_meta_integration(admin_engine, seed.a.id)


@pytest.fixture()
def meta_account_b(admin_engine: Engine, seed: Seed) -> str:
    return _create_meta_integration(admin_engine, seed.b.id, access_token="page-token-b")


def _leadgen_body(page_id: str, leadgen_id: str) -> bytes:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1_700_000_000_000,
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": leadgen_id,
                            "page_id": page_id,
                            "form_id": "form-1",
                            "ad_id": "ad-1",
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def _messenger_body(page_id: str, sender_id: str, mid: str, text_body: str = "Hello") -> bytes:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1_700_000_000_000,
                "messaging": [
                    {
                        "sender": {"id": sender_id},
                        "recipient": {"id": page_id},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": mid, "text": text_body},
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def _signature(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _post(client: TestClient, body: bytes):
    return client.post(
        URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _signature(body),
        },
    )


def _leadgen_route(
    respx_mock: respx.MockRouter,
    leadgen_id: str,
    *,
    full_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
):
    # Default contact data is unique per leadgen id. capture_lead() dedupes by
    # email/phone across tests, which would otherwise merge separate submissions.
    field_data = [
        {"name": "full_name", "values": [full_name or f"Meta Lead {leadgen_id}"]},
        {"name": "email", "values": [email or f"meta-{leadgen_id}@example.com"]},
    ]
    if phone:
        field_data.append({"name": "phone_number", "values": [phone]})
    field_data.append({"name": "budget", "values": ["20 seats"]})

    return respx_mock.get(path__regex=rf"^/v\d+\.\d+/{leadgen_id}$").respond(
        200,
        json={
            "field_data": field_data,
            "ad_id": "ad-1",
            "form_id": "form-1",
        },
    )


def test_leadgen_creates_lead_with_unknown_fields_and_no_automatic_consent(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    leadgen_id = str(uuid.uuid4().int)
    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        route = _leadgen_route(
            mock,
            leadgen_id,
            full_name="Ayesha Rahman",
            email="ayesha@example.com",
            phone="+8801700000000",
        )
        response = _post(hook_client, _leadgen_body(meta_account, leadgen_id))

    assert response.status_code == 200, response.text
    assert response.json()["stored"] == 1
    assert route.call_count == 1

    request = route.calls[0].request
    assert request.url.params["fields"] == "field_data,ad_id,form_id"
    assert request.headers["authorization"] == "Bearer page-access-token"
    assert "access_token" not in str(request.url)

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead = session.scalar(
            select(Lead).where(
                Lead.tenant_id == seed.a.id,
                Lead.source == "facebook_lead_ads",
                Lead.external_id == leadgen_id,
            )
        )
        assert lead is not None
        assert lead.name == "Ayesha Rahman"
        assert lead.email == "ayesha@example.com"
        assert lead.phone == "+8801700000000"
        assert lead.source_campaign == "ad-1"
        assert lead.consent is False
        assert lead.consent_source is None

        interaction = session.scalar(
            select(Interaction).where(
                Interaction.tenant_id == seed.a.id,
                Interaction.lead_id == lead.id,
            )
        )
        assert interaction is not None
        assert interaction.details["fields"]["budget"] == "20 seats"
        assert interaction.details["form_id"] == "form-1"

        event_status = session.scalar(
            text(
                "SELECT status FROM webhook_events "
                "WHERE tenant_id = :t AND provider = 'meta' AND event_id = :e"
            ),
            {"t": seed.a.id, "e": leadgen_id},
        )
        assert event_status == "processed"


def test_duplicate_leadgen_webhook_fetches_graph_only_once(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    leadgen_id = str(uuid.uuid4().int)
    body = _leadgen_body(meta_account, leadgen_id)

    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        route = _leadgen_route(mock, leadgen_id)
        first = _post(hook_client, body)
        second = _post(hook_client, body)

    assert first.status_code == 200 and first.json()["stored"] == 1
    assert second.status_code == 200 and second.json()["duplicates"] == 1
    assert route.call_count == 1

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        count = session.scalar(
            text(
                "SELECT count(*) FROM leads "
                "WHERE tenant_id = :t AND source = 'facebook_lead_ads' AND external_id = :e"
            ),
            {"t": seed.a.id, "e": leadgen_id},
        )
        assert count == 1


def test_lead_fetch_failure_is_recorded_and_webhook_still_returns_200(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    leadgen_id = str(uuid.uuid4().int)
    body = _leadgen_body(meta_account, leadgen_id)

    with respx.mock(base_url="https://graph.facebook.com", assert_all_called=False) as mock:
        mock.get(path__regex=rf"^/v\d+\.\d+/{leadgen_id}$").respond(
            500,
            json={"error": {"code": 2, "message": "temporary failure"}},
        )
        response = _post(hook_client, body)

    assert response.status_code == 200, response.text

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        row = session.execute(
            text(
                "SELECT status, attempts, error FROM webhook_events "
                "WHERE tenant_id = :t AND provider = 'meta' AND event_id = :e"
            ),
            {"t": seed.a.id, "e": leadgen_id},
        ).one()
        assert row.status == "failed"
        assert row.attempts == 1
        assert row.error.startswith("graph_500")
        assert "page-access-token" not in (row.error or "")

        lead_count = session.scalar(
            text(
                "SELECT count(*) FROM leads "
                "WHERE tenant_id = :t AND source = 'facebook_lead_ads' AND external_id = :e"
            ),
            {"t": seed.a.id, "e": leadgen_id},
        )
        assert lead_count == 0


def test_unknown_page_is_acknowledged_without_side_effects(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
):
    leadgen_id = str(uuid.uuid4().int)
    response = _post(hook_client, _leadgen_body(_page_id(), leadgen_id))

    assert response.status_code == 200
    assert response.json()["skipped"] == 1

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        count = session.scalar(
            text("SELECT count(*) FROM webhook_events WHERE event_id = :e"),
            {"e": leadgen_id},
        )
        assert count == 0


def test_messenger_message_creates_messenger_lead_conversation_and_message(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    sender_id = str(uuid.uuid4().int)
    mid = "m." + uuid.uuid4().hex

    response = _post(
        hook_client,
        _messenger_body(meta_account, sender_id, mid, "I need pricing"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["stored"] == 1

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead = session.scalar(
            select(Lead).where(
                Lead.tenant_id == seed.a.id,
                Lead.source == "messenger",
                Lead.external_id == f"messenger:{meta_account}:{sender_id}",
            )
        )
        assert lead is not None
        assert lead.email is None and lead.phone is None
        assert lead.consent is False

        conversation = session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == seed.a.id,
                Conversation.lead_id == lead.id,
                Conversation.channel == "messenger",
            )
        )
        assert conversation is not None
        assert conversation.external_contact_id == sender_id
        assert conversation.last_inbound_at is not None

        message = session.scalar(
            select(Message).where(
                Message.tenant_id == seed.a.id,
                Message.provider == "messenger",
                Message.provider_message_id == mid,
            )
        )
        assert message is not None
        assert message.direction == "inbound"
        assert message.message_text == "I need pricing"


def test_messenger_phone_message_updates_existing_lead(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    sender_id = str(uuid.uuid4().int)
    first_mid = "m." + uuid.uuid4().hex
    phone_mid = "m." + uuid.uuid4().hex

    assert (
        _post(hook_client, _messenger_body(meta_account, sender_id, first_mid)).status_code
        == 200
    )
    response = _post(
        hook_client,
        _messenger_body(
            meta_account,
            sender_id,
            phone_mid,
            "Here is my phone number 01700000000",
        ),
    )

    assert response.status_code == 200, response.text
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead = session.scalar(
            select(Lead).where(
                Lead.tenant_id == seed.a.id,
                Lead.source == "messenger",
                Lead.external_id == f"messenger:{meta_account}:{sender_id}",
            )
        )
        assert lead is not None
        assert lead.phone == "+8801700000000"


def test_messenger_email_message_updates_existing_lead(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    sender_id = str(uuid.uuid4().int)
    first_mid = "m." + uuid.uuid4().hex
    email_mid = "m." + uuid.uuid4().hex

    assert (
        _post(hook_client, _messenger_body(meta_account, sender_id, first_mid)).status_code
        == 200
    )
    response = _post(
        hook_client,
        _messenger_body(
            meta_account,
            sender_id,
            email_mid,
            "My email address is buyer@example.com",
        ),
    )

    assert response.status_code == 200, response.text
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead = session.scalar(
            select(Lead).where(
                Lead.tenant_id == seed.a.id,
                Lead.source == "messenger",
                Lead.external_id == f"messenger:{meta_account}:{sender_id}",
            )
        )
        assert lead is not None
        assert lead.email == "buyer@example.com"


def test_messenger_echo_delivery_and_read_are_not_stored(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    payload = {
        "object": "page",
        "entry": [
            {
                "id": meta_account,
                "messaging": [
                    {
                        "sender": {"id": meta_account},
                        "message": {"mid": "echo-1", "is_echo": True, "text": "sent"},
                    },
                    {"sender": {"id": "customer"}, "delivery": {"mids": ["m.1"]}},
                    {"sender": {"id": "customer"}, "read": {"watermark": 1}},
                ],
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")

    response = _post(hook_client, body)

    assert response.status_code == 200
    assert response.json()["stored"] == 0

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        message_count = session.scalar(
            text(
                "SELECT count(*) FROM messages "
                "WHERE tenant_id = :t AND provider = 'messenger' "
                "AND provider_message_id IN ('echo-1', 'm.1')"
            ),
            {"t": seed.a.id},
        )
        assert message_count == 0


def test_messenger_duplicate_webhook_is_idempotent(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
):
    sender_id = str(uuid.uuid4().int)
    mid = "m." + uuid.uuid4().hex
    body = _messenger_body(meta_account, sender_id, mid)

    first = _post(hook_client, body)
    second = _post(hook_client, body)

    assert first.status_code == 200 and first.json()["stored"] == 1
    assert second.status_code == 200 and second.json()["duplicates"] == 1

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        count = session.scalar(
            text(
                "SELECT count(*) FROM messages "
                "WHERE tenant_id = :t AND provider = 'messenger' AND provider_message_id = :m"
            ),
            {"t": seed.a.id, "m": mid},
        )
        assert count == 1


def test_same_messenger_contact_is_separate_per_tenant(
    hook_client: TestClient,
    admin_engine: Engine,
    seed: Seed,
    meta_account: str,
    meta_account_b: str,
):
    sender_id = str(uuid.uuid4().int)

    assert (
        _post(
            hook_client,
            _messenger_body(meta_account, sender_id, "m." + uuid.uuid4().hex),
        ).status_code
        == 200
    )
    assert (
        _post(
            hook_client,
            _messenger_body(meta_account_b, sender_id, "m." + uuid.uuid4().hex),
        ).status_code
        == 200
    )

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead_a = session.scalar(
            select(Lead).where(
                Lead.tenant_id == seed.a.id,
                Lead.external_id == f"messenger:{meta_account}:{sender_id}",
            )
        )
        assert lead_a is not None

    with Session(admin_engine) as session:
        set_tenant(session, seed.b.id)
        lead_b = session.scalar(
            select(Lead).where(
                Lead.tenant_id == seed.b.id,
                Lead.external_id == f"messenger:{meta_account_b}:{sender_id}",
            )
        )
        assert lead_b is not None
        assert lead_b.id != lead_a.id
