"""Tests for Settings API (/api/v1/settings/automation)."""

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core.tenancy import TenantContext
from app.modules.auth.errors import AuthError
from app.modules.settings import router
from app.modules.settings.models import TenantSettings
from app.modules.settings.schemas import AutomationSettingsUpdate


def setup_context(role="admin"):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    context = TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        membership_id=uuid.uuid4(),
        role=role,
        team_id=None,
        session_id=uuid.uuid4(),
    )
    mock_session = MagicMock()
    return mock_session, context


def test_rep_gets_403_on_get_settings():
    session, context = setup_context(role="rep")
    with pytest.raises(AuthError) as exc_info:
        router.get_automation_settings(context=context, session=session)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"


def test_rep_gets_403_on_put_settings():
    session, context = setup_context(role="rep")
    body = AutomationSettingsUpdate(
        timezone="Asia/Dhaka",
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
    )
    with pytest.raises(AuthError) as exc_info:
        router.put_automation_settings(body=body, context=context, session=session)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"


def test_manager_gets_403_on_settings():
    session, context = setup_context(role="manager")
    with pytest.raises(AuthError) as exc_info:
        router.get_automation_settings(context=context, session=session)
    assert exc_info.value.status_code == 403


def test_admin_gets_default_settings_when_none_exist():
    session, context = setup_context(role="admin")
    session.scalar.return_value = None  # No settings row in DB

    resp = router.get_automation_settings(context=context, session=session)
    data = resp["data"]
    assert data["timezone"] == "Asia/Dhaka"
    assert data["quiet_hours_start"] == "21:00"
    assert data["quiet_hours_end"] == "09:00"


def test_admin_puts_settings_audited():
    session, context = setup_context(role="admin")
    existing = TenantSettings(
        tenant_id=context.tenant_id,
        timezone="Asia/Dhaka",
        quiet_hours_start=datetime.time(21, 0),
        quiet_hours_end=datetime.time(9, 0),
    )
    session.scalar.return_value = existing

    body = AutomationSettingsUpdate(
        timezone="America/New_York",
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
    )

    with patch("app.modules.settings.service.record_audit_event") as mock_audit:
        resp = router.put_automation_settings(
            body=body, context=context, session=session
        )
        data = resp["data"]
        assert data["timezone"] == "America/New_York"
        assert data["quiet_hours_start"] == "22:00"
        assert data["quiet_hours_end"] == "08:00"

        mock_audit.assert_called_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == "settings.automation_updated"
        assert kwargs["tenant_id"] == context.tenant_id
        assert kwargs["actor_user_id"] == context.user_id


def test_admin_invalid_timezone_422():
    with pytest.raises(ValidationError):
        AutomationSettingsUpdate(
            timezone="Invalid/Timezone_Not_Real",
            quiet_hours_start="22:00",
            quiet_hours_end="08:00",
        )


def test_admin_invalid_time_format_422():
    with pytest.raises(ValidationError):
        AutomationSettingsUpdate(
            timezone="Asia/Dhaka",
            quiet_hours_start="25:00",  # invalid hour
            quiet_hours_end="08:00",
        )
