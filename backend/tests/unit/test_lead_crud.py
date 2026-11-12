import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.audit.models import AuditLog
from app.modules.auth.errors import AuthError
from app.modules.leads import crud
from app.modules.leads.models import Interaction, Lead
from app.modules.leads.schemas import LeadCreate, LeadUpdate, NoteCreate


def make_context(role="admin", team_id=None):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=role,
        team_id=team_id,
    )


def make_lead(context, **overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "tenant_id": context.tenant_id,
        "name": "Ayesha Rahman",
        "email": "ayesha@example.com",
        "phone": None,
        "company_name": "Acme",
        "source": "manual",
        "source_campaign": None,
        "external_id": None,
        "status": "new",
        "lost_reason": None,
        "assigned_user_id": None,
        "team_id": None,
        "intent": None,
        "lead_score": None,
        "priority": "medium",
        "consent": False,
        "opted_out": False,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def attach_defaults(session):
    def add(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if isinstance(obj, (Lead, Interaction)):
            now = datetime.now(UTC)
            if getattr(obj, "created_at", None) is None:
                obj.created_at = now
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = now
            if isinstance(obj, Interaction) and getattr(obj, "occurred_at", None) is None:
                obj.occurred_at = now

    session.add.side_effect = add


def test_create_lead_saves_lead_note_audit_and_idempotent_response(monkeypatch):
    session = MagicMock()
    attach_defaults(session)
    context = make_context()
    key_id = uuid.uuid4()
    stored = {}
    monkeypatch.setattr(crud, "_claim_create_idempotency", lambda *args: (key_id, None))
    monkeypatch.setattr(
        crud,
        "_store_create_response",
        lambda _session, _key_id, body: stored.update(body),
    )
    session.scalar.return_value = None

    body = LeadCreate(
        name=" Ayesha Rahman ",
        email="AYESHA@example.com",
        source="manual",
        consent=True,
        notes="  Asked for a demo  ",
    )
    result, replay = crud.create_lead(session, context, body, "request-key-123")

    assert replay is False
    assert result["name"] == "Ayesha Rahman"
    assert result["email"] == "ayesha@example.com"
    assert result["version"] == 1
    assert result["consent"] is True
    assert stored == result
    session.commit.assert_called_once()

    added = [call.args[0] for call in session.add.call_args_list]
    lead = next(item for item in added if isinstance(item, Lead))
    interactions = [item for item in added if isinstance(item, Interaction)]
    audits = [item for item in added if isinstance(item, AuditLog)]
    assert lead.source == "manual"
    assert lead.consent_source == "manual"
    assert {item.type for item in interactions} == {"lead_created", "note"}
    assert any(item.action == "lead.created" for item in audits)


def test_create_lead_replays_existing_idempotency_response(monkeypatch):
    session = MagicMock()
    context = make_context()
    previous = {"id": str(uuid.uuid4()), "name": "Previously created"}
    monkeypatch.setattr(crud, "_claim_create_idempotency", lambda *args: (None, previous))

    result, replay = crud.create_lead(
        session,
        context,
        LeadCreate(name="Ayesha", email="ayesha@example.com"),
        "request-key-123",
    )

    assert replay is True
    assert result == previous
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_create_lead_rejects_duplicate_within_tenant(monkeypatch):
    session = MagicMock()
    context = make_context()
    monkeypatch.setattr(crud, "_claim_create_idempotency", lambda *args: (uuid.uuid4(), None))
    session.scalar.return_value = uuid.uuid4()

    with pytest.raises(AuthError) as exc:
        crud.create_lead(
            session,
            context,
            LeadCreate(name="Ayesha", email="ayesha@example.com"),
            "request-key-123",
        )

    assert exc.value.status_code == 409
    assert exc.value.code == "duplicate_lead"
    assert exc.value.details[0]["existing_lead_id"] == str(session.scalar.return_value)
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_list_leads_returns_cursor_and_metadata():
    session = MagicMock()
    context = make_context()
    first = make_lead(context)
    second = make_lead(context, id=uuid.uuid4(), created_at=first.created_at)
    session.scalars.return_value.all.return_value = [first, second]

    data, meta = crud.list_leads(
        session,
        context,
        q="Ayesha",
        status=["new,contacted"],
        source=["manual"],
        priority="medium",
        sort="-created_at",
        limit=1,
    )

    assert len(data) == 1
    assert meta["has_more"] is True
    assert meta["next_cursor"]
    value, lead_id = crud._decode_cursor(meta["next_cursor"], "created_at", True)
    assert value == first.created_at
    assert lead_id == first.id


def test_list_leads_rejects_unknown_filter_and_sort():
    session = MagicMock()
    context = make_context()

    with pytest.raises(AuthError):
        crud.list_leads(session, context, status=["made_up"])

    with pytest.raises(AuthError):
        crud.list_leads(session, context, sort="password")


def test_list_leads_rejects_malformed_cursor():
    with pytest.raises(AuthError) as exc:
        crud._decode_cursor("not-a-cursor", "created_at", True)
    assert exc.value.status_code == 400


def test_update_lead_checks_version_and_records_status_change():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context)
    session.scalar.return_value = lead

    result = crud.update_lead(
        session,
        context,
        lead.id,
        LeadUpdate(version=1, status="contacted"),
    )

    assert result["status"] == "contacted"
    assert result["version"] == 2
    added = [call.args[0] for call in session.add.call_args_list]
    assert any(
        isinstance(item, Interaction)
        and item.type == "status_change"
        and item.details["from"] == "new"
        and item.details["to"] == "contacted"
        for item in added
    )
    assert any(
        isinstance(item, AuditLog) and item.action == "lead.status_changed"
        for item in added
    )
    session.commit.assert_called_once()


def test_update_lead_rejects_stale_version():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context, version=3)
    session.scalar.return_value = lead

    with pytest.raises(AuthError) as exc:
        crud.update_lead(
            session,
            context,
            lead.id,
            LeadUpdate(version=2, priority="high"),
        )

    assert exc.value.code == "version_conflict"
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_update_lead_rejects_duplicate_email():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context)
    session.scalar.side_effect = [lead, uuid.uuid4(), None]

    with pytest.raises(AuthError) as exc:
        crud.update_lead(
            session,
            context,
            lead.id,
            LeadUpdate(version=1, email="other@example.com"),
        )

    assert exc.value.code == "duplicate_lead"
    session.rollback.assert_called_once()


def test_add_note_persists_interaction_and_audit():
    session = MagicMock()
    attach_defaults(session)
    context = make_context()
    lead = make_lead(context)
    session.scalar.return_value = lead

    result = crud.add_note(
        session,
        context,
        lead.id,
        NoteCreate(text="  Customer requested a call  "),
    )

    assert result["type"] == "note"
    assert result["text"] == "Customer requested a call"
    added = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(item, Interaction) and item.type == "note" for item in added)
    assert any(
        isinstance(item, AuditLog) and item.action == "lead.note_added"
        for item in added
    )
    session.commit.assert_called_once()


def test_create_schema_requires_email_or_phone_and_valid_source():
    with pytest.raises(ValueError):
        LeadCreate(name="Ayesha")
    with pytest.raises(ValueError):
        LeadCreate(name="Ayesha", email="a@example.com", source="unknown")

def test_idempotency_key_replays_matching_request():
    context = make_context()
    key = "request-key-123"
    body = LeadCreate(name="Ayesha", email="ayesha@example.com")
    request_hash = crud._request_hash(body)
    previous = SimpleNamespace(
        request_hash=request_hash,
        response_status=201,
        response_body={"id": str(uuid.uuid4()), "name": "Ayesha"},
    )
    session = MagicMock()
    session.scalar.side_effect = [None, previous]

    key_id, replay = crud._claim_create_idempotency(
        session, context, key, request_hash
    )

    assert key_id is None
    assert replay == previous.response_body


def test_idempotency_key_rejects_different_request_body():
    context = make_context()
    previous = SimpleNamespace(
        request_hash="different-hash",
        response_status=201,
        response_body={"id": str(uuid.uuid4())},
    )
    session = MagicMock()
    session.scalar.side_effect = [None, previous]

    with pytest.raises(AuthError) as exc:
        crud._claim_create_idempotency(
            session,
            context,
            "request-key-123",
            "current-request-hash",
        )

    assert exc.value.code == "idempotency_conflict"


def test_request_hash_is_stable_for_normalized_schema_values():
    first = LeadCreate(name="Ayesha", email="AYESHA@example.com")
    second = LeadCreate(name="Ayesha", email="ayesha@example.com")
    assert crud._request_hash(first) == crud._request_hash(second)

def test_get_lead_includes_latest_assessment_by_default():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context)
    session.scalar.side_effect = [lead, None]

    result = crud.get_lead(session, context, lead.id)

    assert result["id"] == str(lead.id)
    assert "latest_assessment" in result
    assert result["latest_assessment"] is None


def test_get_lead_rejects_unknown_expansion():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context)
    session.scalar.return_value = lead

    with pytest.raises(AuthError) as exc:
        crud.get_lead(session, context, lead.id, ["password_hash"])

    assert exc.value.status_code == 422

def test_duplicate_error_does_not_reveal_a_lead_outside_rep_scope():
    session = MagicMock()
    context = make_context(role="rep")
    existing_id = uuid.uuid4()
    session.scalar.side_effect = [existing_id, None]

    with pytest.raises(AuthError) as exc:
        crud._check_duplicate(
            session,
            context,
            email="shared@example.com",
            phone=None,
        )

    assert exc.value.code == "duplicate_lead"
    assert exc.value.details == []


def test_phone_normalization_rejects_letters_and_accepts_common_formatting():
    from app.modules.leads.schemas import _clean_phone

    assert _clean_phone("+880 (170) 000-0000") == "+8801700000000"
    with pytest.raises(ValueError):
        _clean_phone("call-me-01700000000")

def test_update_lead_requires_lost_reason_and_records_it():
    session = MagicMock()
    context = make_context()
    lead = make_lead(context)
    session.scalar.return_value = lead

    result = crud.update_lead(
        session,
        context,
        lead.id,
        LeadUpdate(version=1, status="lost", lost_reason="price"),
    )

    assert result["status"] == "lost"
    assert result["lost_reason"] == "price"
    added = [call.args[0] for call in session.add.call_args_list]
    event = next(
        item for item in added
        if isinstance(item, Interaction) and item.type == "status_change"
    )
    assert event.details["reason"] == "price"


def test_admin_can_reopen_lost_lead_with_a_reason():
    session = MagicMock()
    context = make_context(role="admin")
    lead = make_lead(context, status="lost", lost_reason="timing")
    session.scalar.return_value = lead

    result = crud.update_lead(
        session,
        context,
        lead.id,
        LeadUpdate(
            version=1,
            status="contacted",
            reopen_reason="Customer contacted us again",
        ),
    )

    assert result["status"] == "contacted"
    assert result["lost_reason"] is None
    added = [call.args[0] for call in session.add.call_args_list]
    event = next(
        item for item in added
        if isinstance(item, Interaction) and item.type == "status_change"
    )
    assert event.details["reason"] == "Customer contacted us again"


def test_rep_cannot_reopen_lost_lead():
    session = MagicMock()
    context = make_context(role="rep")
    lead = make_lead(context, status="lost", lost_reason="timing")
    session.scalar.return_value = lead

    with pytest.raises(AuthError) as exc:
        crud.update_lead(
            session,
            context,
            lead.id,
            LeadUpdate(
                version=1,
                status="contacted",
                reopen_reason="Customer contacted us again",
            ),
        )

    assert exc.value.status_code == 403
    session.rollback.assert_called_once()

