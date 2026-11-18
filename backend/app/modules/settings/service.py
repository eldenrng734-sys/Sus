import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.service import record_audit_event
from app.modules.settings.models import TenantSettings
from app.modules.settings.schemas import AutomationSettingsUpdate

DEFAULT_TIMEZONE = "Asia/Dhaka"
DEFAULT_QUIET_HOURS_START = time(21, 0)
DEFAULT_QUIET_HOURS_END = time(9, 0)


def get_tenant_settings(
    session: Session,
    tenant_id: uuid.UUID,
) -> TenantSettings | None:
    return session.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))


def is_quiet_hours(
    session: Session,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
    settings: TenantSettings | None = None,
) -> tuple[bool, datetime | None]:
    """Determine whether the given or current time falls within tenant quiet hours.

    Returns:
        (True, next_window_end_utc) if in quiet hours.
        (False, None) if not in quiet hours.
    """
    if settings is None:
        settings = get_tenant_settings(session, tenant_id)

    tz_name = settings.timezone if settings else DEFAULT_TIMEZONE
    start = settings.quiet_hours_start if settings else DEFAULT_QUIET_HOURS_START
    end = settings.quiet_hours_end if settings else DEFAULT_QUIET_HOURS_END

    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    local_time = local_now.time()

    if start > end:
        # Crosses midnight (e.g. 21:00 to 09:00)
        if local_time >= start:
            target_date = local_now.date() + timedelta(days=1)
            target_local = datetime.combine(target_date, end, tzinfo=tz)
            return True, target_local.astimezone(UTC)
        if local_time < end:
            target_date = local_now.date()
            target_local = datetime.combine(target_date, end, tzinfo=tz)
            return True, target_local.astimezone(UTC)
        return False, None
    else:
        # Same-day window (e.g. 01:00 to 05:00)
        if start <= local_time < end:
            target_date = local_now.date()
            target_local = datetime.combine(target_date, end, tzinfo=tz)
            return True, target_local.astimezone(UTC)
        return False, None


def update_automation_settings(
    session: Session,
    tenant_id: uuid.UUID,
    data: AutomationSettingsUpdate,
    user_id: uuid.UUID | None = None,
) -> TenantSettings:
    settings = get_tenant_settings(session, tenant_id)

    start_h, start_m = map(int, data.quiet_hours_start.split(":"))
    end_h, end_m = map(int, data.quiet_hours_end.split(":"))

    if settings is None:
        settings = TenantSettings(
            tenant_id=tenant_id,
            timezone=data.timezone,
            quiet_hours_start=time(start_h, start_m),
            quiet_hours_end=time(end_h, end_m),
        )
        session.add(settings)
    else:
        settings.timezone = data.timezone
        settings.quiet_hours_start = time(start_h, start_m)
        settings.quiet_hours_end = time(end_h, end_m)

    record_audit_event(
        session,
        action="settings.automation_updated",
        actor_type="user",
        tenant_id=tenant_id,
        actor_user_id=user_id,
        entity_type="tenant_settings",
        entity_id=tenant_id,
        details={
            "timezone": data.timezone,
            "quiet_hours_start": data.quiet_hours_start,
            "quiet_hours_end": data.quiet_hours_end,
        },
    )
    session.flush()
    return settings
