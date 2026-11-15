import hashlib
import hmac
import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_session
from app.main import auth_error_handler
from app.modules.auth.errors import AuthError
from app.modules.conversations.models import Conversation, Message
from app.modules.integrations.webhook_router import router as webhook_router
from app.modules.leads.models import Lead
from tests.cross_tenant.support import set_tenant

SECRET = "whatsapp-test-secret"
VERIFY_TOKEN = "test-verify-token"
URL = "/api/v1/webhooks/whatsapp"


@pytest.fixture(scope="module", autouse=True)
def _secrets():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "meta_app_secret", SecretStr(SECRET))
        patch.setattr(settings, "webhook_verify_token", SecretStr(VERIFY_TOKEN))
        yield


@pytest.fixture(scope="module")
def hook_client(admin_engine):
    mini = FastAPI()
    mini.add_exception_handler(AuthError, auth_error_handler)
    mini.include_router(webhook_router)

    def _session():
        with Session(admin_engine) as session:
            yield session

    mini.dependency_overrides[get_session] = _session
    return TestClient(mini, client=("127.0.0.1", 50000))


@pytest.fixture(scope="module")
def wa_account_a(admin_engine, seed):
    account_id = "wa-acc-a-" + uuid.uuid4().hex[:8]
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        conn.execute(
            text(
                "INSERT INTO integrations (tenant_id, provider, provider_account_id, status) "
                "VALUES (:t, 'whatsapp', :a, 'active')"
            ),
            {"t": seed.a.id, "a": account_id},
        )
    return account_id


@pytest.fixture(scope="module")
def wa_account_b(admin_engine, seed):
    account_id = "wa-acc-b-" + uuid.uuid4().hex[:8]
    with admin_engine.begin() as conn:
        set_tenant(conn, seed.b.id)
        conn.execute(
            text(
                "INSERT INTO integrations (tenant_id, provider, provider_account_id, status) "
                "VALUES (:t, 'whatsapp', :a, 'active')"
            ),
            {"t": seed.b.id, "a": account_id},
        )
    return account_id


def _whatsapp_payload(account_id: str, message_id: str, sender: str, text_body: str, sender_name: str | None = None):
    msg = {
        "id": message_id,
        "from": sender,
        "type": "text",
        "text": {"body": text_body},
        "timestamp": "1700000000",
    }
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": account_id},
        "contacts": [{"wa_id": sender, "profile": {"name": sender_name or "Test User"}}],
        "messages": [msg],
    }
    payload = {"entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": value}]}]}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _status_payload(account_id: str, message_id: str, status_str: str, recipient: str = "8801700000000"):
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": account_id},
        "statuses": [
            {
                "id": message_id,
                "status": status_str,
                "timestamp": "1700000005",
                "recipient_id": recipient,
            }
        ],
    }
    payload = {"entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": value}]}]}
    return json.dumps(payload).encode("utf-8")


def _sig(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _post(client, body: bytes, signature: str | None = None):
    headers = {"Content-Type": "application/json"}
    sig_header = signature or _sig(body)
    headers["X-Hub-Signature-256"] = sig_header
    return client.post(URL, content=body, headers=headers)


def test_handshake_verification(hook_client):
    # Valid handshake
    params = {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "123456"}
    res = hook_client.get(URL, params=params)
    assert res.status_code == 200
    assert res.text == "123456"

    # Invalid token returns 403
    bad_params = {"hub.mode": "subscribe", "hub.verify_token": "wrong-token", "hub.challenge": "123456"}
    bad_res = hook_client.get(URL, params=bad_params)
    assert bad_res.status_code == 403


def test_inbound_message_creates_lead_conversation_and_message(hook_client, admin_engine, seed, wa_account_a):
    mid = "wamid.inbound." + uuid.uuid4().hex
    raw_phone = "01712345678"  # Bangladesh local format -> should normalize to +8801712345678
    body = _whatsapp_payload(wa_account_a, mid, raw_phone, "Hello, I want to buy!", "Tanvir Ahmed")

    resp = _post(hook_client, body)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["stored"] == 1

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)

        # 1. Lead created via capture service with normalized E.164 phone
        lead = session.query(Lead).filter(Lead.tenant_id == seed.a.id, Lead.phone == "+8801712345678").first()
        assert lead is not None
        assert lead.name == "Tanvir Ahmed"
        assert lead.source == "whatsapp"

        # 2. Conversation created with last_inbound_at populated
        conv = session.query(Conversation).filter(
            Conversation.tenant_id == seed.a.id,
            Conversation.lead_id == lead.id,
            Conversation.channel == "whatsapp",
        ).first()
        assert conv is not None
        assert conv.last_inbound_at is not None
        assert conv.external_contact_id == "+8801712345678"

        # 3. Inbound message inserted
        msg = session.query(Message).filter(
            Message.tenant_id == seed.a.id,
            Message.conversation_id == conv.id,
            Message.provider_message_id == mid,
        ).first()
        assert msg is not None
        assert msg.direction == "inbound"
        assert msg.message_text == "Hello, I want to buy!"
        assert msg.status == "received"


def test_duplicate_delivery_deduplicated_and_idempotent(hook_client, admin_engine, seed, wa_account_a):
    mid = "wamid.dup." + uuid.uuid4().hex
    body = _whatsapp_payload(wa_account_a, mid, "01811112233", "Double message")

    # Send first time
    r1 = _post(hook_client, body)
    assert r1.status_code == 200
    assert r1.json()["stored"] == 1

    # Send second time (same payload)
    r2 = _post(hook_client, body)
    assert r2.status_code == 200
    assert r2.json()["duplicates"] == 1

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        count = session.query(Message).filter(
            Message.tenant_id == seed.a.id,
            Message.provider_message_id == mid,
        ).count()
        assert count == 1


def test_bangla_and_emoji_text_stored_correctly(hook_client, admin_engine, seed, wa_account_a):
    mid = "wamid.utf8." + uuid.uuid4().hex
    bangla_emoji = "হ্যালো, আমি বিস্তারিত জানতে চাই! 🎉🚀"
    body = _whatsapp_payload(wa_account_a, mid, "01999998888", bangla_emoji, "রফিক")

    resp = _post(hook_client, body)
    assert resp.status_code == 200

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        msg = session.query(Message).filter(
            Message.tenant_id == seed.a.id,
            Message.provider_message_id == mid,
        ).first()
        assert msg is not None
        assert msg.message_text == bangla_emoji


def test_stop_keyword_triggers_optout(hook_client, admin_engine, seed, wa_account_a):
    phone = "01755554444"
    e164 = "+8801755554444"

    # Step 1: Initial message
    mid1 = "wamid.opt1." + uuid.uuid4().hex
    _post(hook_client, _whatsapp_payload(wa_account_a, mid1, phone, "Hi"))

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead = session.query(Lead).filter(Lead.tenant_id == seed.a.id, Lead.phone == e164).first()
        assert lead is not None
        assert lead.opted_out is False

    # Step 2: Customer sends Bangla STOP keyword "বন্ধ"
    mid2 = "wamid.opt2." + uuid.uuid4().hex
    _post(hook_client, _whatsapp_payload(wa_account_a, mid2, phone, "বন্ধ"))

    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead = session.query(Lead).filter(Lead.tenant_id == seed.a.id, Lead.phone == e164).first()
        assert lead is not None
        assert lead.opted_out is True
        assert lead.opted_out_source == "whatsapp"


def test_two_tenants_same_customer_number_get_separate_leads(hook_client, admin_engine, seed, wa_account_a, wa_account_b):
    customer_phone = "01700112233"
    mid_a = "wamid.a." + uuid.uuid4().hex
    mid_b = "wamid.b." + uuid.uuid4().hex

    # Customer messages Company A
    bodyA = _whatsapp_payload(wa_account_a, mid_a, customer_phone, "Message to A")
    resA = _post(hook_client, bodyA)
    assert resA.status_code == 200

    # Same customer messages Company B
    bodyB = _whatsapp_payload(wa_account_b, mid_b, customer_phone, "Message to B")
    resB = _post(hook_client, bodyB)
    assert resB.status_code == 200

    # Verify Company A has its own lead
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        lead_a = session.query(Lead).filter(Lead.tenant_id == seed.a.id, Lead.phone == "+8801700112233").first()
        assert lead_a is not None

    # Verify Company B has its own distinct lead
    with Session(admin_engine) as session:
        set_tenant(session, seed.b.id)
        lead_b = session.query(Lead).filter(Lead.tenant_id == seed.b.id, Lead.phone == "+8801700112233").first()
        assert lead_b is not None
        assert lead_b.id != lead_a.id


def test_status_update_does_not_create_lead(hook_client, admin_engine, seed, wa_account_a):
    wamid = "wamid.status." + uuid.uuid4().hex
    status_body = _status_payload(wa_account_a, wamid, "delivered")

    res = _post(hook_client, status_body)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Status receipts do not create leads or conversations
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        msg_count = session.query(Message).filter(Message.provider_message_id == wamid).count()
        assert msg_count == 0


def test_unknown_phone_number_id_returns_200_and_processes_nothing(hook_client, admin_engine, seed):
    mid = "wamid.unknown." + uuid.uuid4().hex
    body = _whatsapp_payload("unknown_phone_number_id", mid, "01700000000", "Hello")

    res = _post(hook_client, body)
    assert res.status_code == 200
    assert res.json()["skipped"] == 1

    # Nothing stored
    with Session(admin_engine) as session:
        set_tenant(session, seed.a.id)
        count = session.query(Message).filter(Message.provider_message_id == mid).count()
        assert count == 0

