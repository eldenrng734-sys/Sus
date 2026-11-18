"""Unit tests for primary lead form embed endpoint (Step #21)."""

import uuid
from unittest.mock import MagicMock

from app.core.tenancy import TenantContext
from app.modules.lead_forms import router
from app.modules.lead_forms.models import LeadForm


def test_get_existing_primary_lead_form():
    tenant_id = uuid.uuid4()
    context = TenantContext(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role="admin",
        team_id=None,
        session_id=uuid.uuid4(),
    )
    existing_form = LeadForm(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        public_id="lf_test12345",
        name="Existing Form",
        allowed_fields=["name", "email", "phone"],
        consent_text="Consent test",
        is_active=True,
    )
    session = MagicMock()
    session.scalar.return_value = existing_form

    resp = router.get_primary_lead_form(context=context, session=session)
    assert resp["data"]["public_id"] == "lf_test12345"
    assert resp["data"]["name"] == "Existing Form"
    assert "lf_test12345" in resp["data"]["embed_code"]
    assert "/api/v1/public/forms/lf_test12345/submit" in resp["data"]["embed_code"]
    session.add.assert_not_called()


def test_auto_create_primary_lead_form_when_none_exists():
    tenant_id = uuid.uuid4()
    context = TenantContext(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        role="admin",
        team_id=None,
        session_id=uuid.uuid4(),
    )
    session = MagicMock()
    session.scalar.return_value = None  # No existing form

    resp = router.get_primary_lead_form(context=context, session=session)
    assert resp["data"]["public_id"].startswith("lf_")
    assert resp["data"]["name"] == "Website Contact Form"
    assert resp["data"]["is_active"] is True
    assert "embed_code" in resp["data"]
    session.add.assert_called_once()
    session.commit.assert_called_once()
