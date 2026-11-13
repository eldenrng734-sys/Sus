"""Capture service tests against a real PostgreSQL. Each test is rolled back."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import set_tenant_context
from app.modules.leads.capture import CaptureError, CaptureInput, capture_lead
from app.modules.leads.models import Interaction, Lead


@pytest.fixture
def db(admin_engine):
    conn = admin_engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


def _uniq() -> str:
    return uuid.uuid4().hex[:10]


def _phone() -> str:
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _as_tenant(db: Session, tenant) -> None:
    set_tenant_context(db, str(tenant.id))


def test_new_lead_is_created(db, seed):
    _as_tenant(db, seed.a)
    result = capture_lead(
        db,
        tenant_id=seed.a.id,
        data=CaptureInput(name="Ayesha", email=f"{_uniq()}@example.com", source="manual"),
    )
    assert result.created is True
    assert result.matched_on is None
    assert result.lead.tenant_id == seed.a.id
    assert result.lead.status == "new"


def test_same_email_with_different_case_matches(db, seed):
    _as_tenant(db, seed.a)
    email = f"{_uniq()}@example.com"
    first = capture_lead(
        db, tenant_id=seed.a.id, data=CaptureInput(name="Ayesha", email=email)
    )
    second = capture_lead(
        db,
        tenant_id=seed.a.id,
        data=CaptureInput(name="Ayesha R", email=f"  {email.upper()} "),
    )
    assert second.created is False
    assert second.matched_on == "email"
    assert second.lead.id == first.lead.id


def test_phone_formats_match(db, seed):
    _as_tenant(db, seed.a)
    phone = _phone()
    first = capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="A", phone=phone))
    local = "0" + phone[4:]  # +880 1xxxxxxxxx  ->  01xxxxxxxxx
    second = capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="A", phone=local))
    assert second.created is False
    assert second.matched_on == "phone"
    assert second.lead.id == first.lead.id


def test_external_id_matches_even_with_new_email(db, seed):
    _as_tenant(db, seed.a)
    ext = _uniq()
    first = capture_lead(
        db,
        tenant_id=seed.a.id,
        data=CaptureInput(
            name="W", email=f"{_uniq()}@example.com", source="whatsapp", external_id=ext
        ),
    )
    second = capture_lead(
        db,
        tenant_id=seed.a.id,
        data=CaptureInput(
            name="W", email=f"{_uniq()}@example.com", source="whatsapp", external_id=ext
        ),
    )
    assert second.created is False
    assert second.matched_on == "external_id"
    assert second.lead.id == first.lead.id


def test_other_tenant_with_same_email_is_a_separate_lead(db, seed):
    email = f"{_uniq()}@example.com"
    _as_tenant(db, seed.a)
    a = capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="X", email=email))
    _as_tenant(db, seed.b)
    b = capture_lead(db, tenant_id=seed.b.id, data=CaptureInput(name="X", email=email))
    assert a.created is True and b.created is True
    assert a.lead.id != b.lead.id
    assert b.lead.tenant_id == seed.b.id


def test_missing_contact_is_rejected(db, seed):
    _as_tenant(db, seed.a)
    with pytest.raises(CaptureError):
        capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="No contact"))


def test_unknown_source_is_rejected(db, seed):
    _as_tenant(db, seed.a)
    with pytest.raises(CaptureError):
        capture_lead(
            db,
            tenant_id=seed.a.id,
            data=CaptureInput(name="X", email=f"{_uniq()}@example.com", source="carrier-pigeon"),
        )


def test_wrong_tenant_context_is_rejected(db, seed):
    _as_tenant(db, seed.b)  # context says B ...
    with pytest.raises(CaptureError):
        capture_lead(  # ... but the caller claims A
            db,
            tenant_id=seed.a.id,
            data=CaptureInput(name="X", email=f"{_uniq()}@example.com"),
        )


def test_two_matching_leads_report_a_conflict(db, seed):
    _as_tenant(db, seed.a)
    e1, p1, e2, p2 = f"{_uniq()}@example.com", _phone(), f"{_uniq()}@example.com", _phone()
    first = capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="One", email=e1, phone=p1))
    second = capture_lead(
        db, tenant_id=seed.a.id, data=CaptureInput(name="Two", email=e2, phone=p2)
    )
    assert first.created and second.created
    result = capture_lead(
        db, tenant_id=seed.a.id, data=CaptureInput(name="Mixed", email=e1, phone=p2)
    )
    assert result.created is False
    assert result.lead.id == first.lead.id
    assert result.conflicts == [second.lead.id]


def test_repeat_capture_fills_blanks_but_never_overwrites_or_downgrades(db, seed):
    _as_tenant(db, seed.a)
    email = f"{_uniq()}@example.com"
    first = capture_lead(
        db, tenant_id=seed.a.id, data=CaptureInput(name="Original", email=email, consent=True)
    )
    second = capture_lead(
        db,
        tenant_id=seed.a.id,
        data=CaptureInput(name="Changed", email=email, company_name="Acme", consent=False),
    )
    assert second.lead.id == first.lead.id
    assert second.lead.name == "Original"
    assert second.lead.company_name == "Acme"
    assert second.lead.consent is True


def test_every_capture_adds_an_interaction(db, seed):
    _as_tenant(db, seed.a)
    email = f"{_uniq()}@example.com"
    first = capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="I", email=email))
    capture_lead(db, tenant_id=seed.a.id, data=CaptureInput(name="I", email=email))
    count = len(db.scalars(select(Interaction).where(Interaction.lead_id == first.lead.id)).all())
    assert count == 2
    assert db.get(Lead, first.lead.id) is not None