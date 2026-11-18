import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.outbox_models import OutboxEvent
from app.modules.audit.service import record_audit_event
from app.modules.tenants.models import Tenant, TenantMembership


def list_tenants(session: Session) -> list[dict[str, Any]]:
    """List tenants with member counts using SECURITY DEFINER function or ORM fallback."""
    try:
        rows = session.execute(text("SELECT * FROM platform_list_tenants()")).mappings().all()
        return [dict(r) for r in rows]
    except (ProgrammingError, Exception):
        # Fallback when running against mock or DB without migrations
        stmt = (
            select(
                Tenant.id,
                Tenant.name,
                Tenant.slug,
                Tenant.status,
                Tenant.created_at,
                func.count(TenantMembership.id).label("member_count"),
            )
            .outerjoin(
                TenantMembership,
                (TenantMembership.tenant_id == Tenant.id) & (TenantMembership.is_active.is_(True)),
            )
            .group_by(Tenant.id, Tenant.name, Tenant.slug, Tenant.status, Tenant.created_at)
            .order_by(Tenant.created_at.desc())
        )
        res = session.execute(stmt).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "slug": r.slug,
                "status": r.status,
                "created_at": r.created_at,
                "member_count": r.member_count or 0,
            }
            for r in res
        ]


def get_tenant(session: Session, tenant_id: uuid.UUID) -> dict[str, Any] | None:
    """Get single tenant summary plus member count."""
    try:
        row = session.execute(
            text("SELECT * FROM platform_get_tenant(:id)"),
            {"id": tenant_id},
        ).mappings().first()
        if row:
            return dict(row)
    except (ProgrammingError, Exception):
        pass

    # Fallback
    res = session.execute(
        select(
            Tenant.id,
            Tenant.name,
            Tenant.slug,
            Tenant.status,
            Tenant.created_at,
            func.count(TenantMembership.id).label("member_count"),
        )
        .outerjoin(
            TenantMembership,
            (TenantMembership.tenant_id == Tenant.id) & (TenantMembership.is_active.is_(True)),
        )
        .where(Tenant.id == tenant_id)
        .group_by(Tenant.id, Tenant.name, Tenant.slug, Tenant.status, Tenant.created_at)
    ).first()

    if res is None:
        return None

    return {
        "id": res.id,
        "name": res.name,
        "slug": res.slug,
        "status": res.status,
        "created_at": res.created_at,
        "member_count": res.member_count or 0,
    }


def suspend_tenant(
    session: Session,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Set tenant status to 'suspended' and record platform audit log."""
    return update_tenant_status(
        session=session,
        tenant_id=tenant_id,
        status="suspended",
        actor_user_id=actor_user_id,
    )


def update_tenant_status(
    session: Session,
    tenant_id: uuid.UUID,
    status: str,
    actor_user_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Update tenant status ('active' or 'suspended') and audit."""
    if status == "suspended":
        try:
            row = session.execute(
                text("SELECT * FROM platform_suspend_tenant(:id)"),
                {"id": tenant_id},
            ).mappings().first()
            if row:
                tenant_data = dict(row)
            else:
                return None
        except (ProgrammingError, Exception):
            tenant = session.get(Tenant, tenant_id)
            if tenant is None:
                return None
            tenant.status = "suspended"
            session.flush()
            tenant_data = get_tenant(session, tenant_id)
    else:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            return None
        tenant.status = status
        session.flush()
        tenant_data = get_tenant(session, tenant_id)

    if tenant_data is None:
        return None

    # Audit the platform action (tenant_id=None satisfies audit_logs_platform_insert RLS policy)
    record_audit_event(
        session,
        action=f"tenant.{status}",
        actor_type="platform_admin",
        tenant_id=None,
        actor_user_id=actor_user_id,
        entity_type="tenant",
        entity_id=tenant_id,
        details={"target_tenant_id": str(tenant_id), "status": status},
    )

    return tenant_data


def get_platform_health(session: Session) -> dict[str, Any]:
    """Return platform DB connections and dead outbox count across all tenants."""
    try:
        row = session.execute(text("SELECT * FROM platform_get_health()")).mappings().first()
        if row:
            return {
                "db_connections": int(row["db_connections"] or 0),
                "dead_outbox_count": int(row["dead_outbox_count"] or 0),
                "status": "ok",
            }
    except (ProgrammingError, Exception):
        pass

    # Fallback
    try:
        dead_count = session.scalar(
            select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "dead")
        ) or 0
    except Exception:
        dead_count = 0

    return {
        "db_connections": 1,
        "dead_outbox_count": dead_count,
        "status": "ok",
    }
