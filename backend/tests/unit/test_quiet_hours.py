"""Unit tests for quiet hours calculation and helper."""

import uuid
from datetime import UTC, datetime, time
from unittest.mock import MagicMock

from app.modules.settings.service import is_quiet_hours


def test_quiet_hours_default_window_in_evening():
    """At 22:00 Dhaka time (16:00 UTC), quiet hours is active (window 21:00 - 09:00).
    Next window end is tomorrow 09:00 Dhaka time (03:00 UTC).
    """
    tenant_id = uuid.uuid4()
    session = MagicMock()

    # Mock get_tenant_settings
    settings_obj = MagicMock()
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.quiet_hours_start = time(21, 0)
    settings_obj.quiet_hours_end = time(9, 0)

    # 2026-11-18 16:00:00 UTC = 2026-11-18 22:00:00 Dhaka
    now_utc = datetime(2026, 11, 18, 16, 0, 0, tzinfo=UTC)

    active, end_utc = is_quiet_hours(session, tenant_id, now=now_utc, settings=settings_obj)

    assert active is True
    # Window ends next morning at 09:00 Dhaka = 03:00 UTC on Nov 19
    expected_end = datetime(2026, 11, 19, 3, 0, 0, tzinfo=UTC)
    assert end_utc == expected_end


def test_quiet_hours_default_window_in_early_morning():
    """At 03:00 Dhaka time (21:00 UTC on Nov 18), quiet hours is active.
    Next window end is today 09:00 Dhaka time (03:00 UTC on Nov 19).
    """
    tenant_id = uuid.uuid4()
    session = MagicMock()

    settings_obj = MagicMock()
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.quiet_hours_start = time(21, 0)
    settings_obj.quiet_hours_end = time(9, 0)

    # 2026-11-18 21:30:00 UTC = 2026-11-19 03:30:00 Dhaka
    now_utc = datetime(2026, 11, 18, 21, 30, 0, tzinfo=UTC)

    active, end_utc = is_quiet_hours(session, tenant_id, now=now_utc, settings=settings_obj)

    assert active is True
    expected_end = datetime(2026, 11, 19, 3, 0, 0, tzinfo=UTC)
    assert end_utc == expected_end


def test_quiet_hours_daytime_not_active():
    """At 14:00 Dhaka time (08:00 UTC), quiet hours is NOT active."""
    tenant_id = uuid.uuid4()
    session = MagicMock()

    settings_obj = MagicMock()
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.quiet_hours_start = time(21, 0)
    settings_obj.quiet_hours_end = time(9, 0)

    # 2026-11-18 08:00:00 UTC = 2026-11-18 14:00:00 Dhaka
    now_utc = datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC)

    active, end_utc = is_quiet_hours(session, tenant_id, now=now_utc, settings=settings_obj)

    assert active is False
    assert end_utc is None


def test_quiet_hours_boundary_conditions():
    tenant_id = uuid.uuid4()
    session = MagicMock()

    settings_obj = MagicMock()
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.quiet_hours_start = time(21, 0)
    settings_obj.quiet_hours_end = time(9, 0)

    # Exactly 21:00:00 Dhaka = 15:00:00 UTC -> should be quiet hours
    start_utc = datetime(2026, 11, 18, 15, 0, 0, tzinfo=UTC)
    active, end_utc = is_quiet_hours(session, tenant_id, now=start_utc, settings=settings_obj)
    assert active is True
    assert end_utc == datetime(2026, 11, 19, 3, 0, 0, tzinfo=UTC)

    # Exactly 09:00:00 Dhaka = 03:00:00 UTC -> window has ended
    end_boundary_utc = datetime(2026, 11, 19, 3, 0, 0, tzinfo=UTC)
    active, end_utc = is_quiet_hours(
        session, tenant_id, now=end_boundary_utc, settings=settings_obj
    )
    assert active is False
    assert end_utc is None
