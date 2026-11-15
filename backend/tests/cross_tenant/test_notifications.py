import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.service_auth import InternalServiceContext
from app.modules.auth.errors import AuthError
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationCreateRequest
from tests.cross_tenant.support import set_tenant


def _insert_notification(conn, tenant_id, user_id, lead_id, notification_id):
    conn.execute(
        text(
            "INSERT INTO notifications "
            "(id, tenant_id, user_id, type, title, body, entity_type, entity_id) "
            "VALUES (:id, :tenant_id, :user_id, 'new_lead', 'New lead', "
            "'A new lead is assigned to you.', 'lead', :lead_id)"
        ),
        {
            "id": notification_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "lead_id": lead_id,
        },
    )


def test_notification_recipient_composite_foreign_key_blocks_other_tenant(
    admin_engine,
    seed,
):
    foreign_user_id = seed.b.users["rep"][0]

    with pytest.raises(IntegrityError, match="foreign key"):
        with admin_engine.begin() as conn:
            set_tenant(conn, seed.a.id)
            _insert_notification(
                conn,
                seed.a.id,
                foreign_user_id,
                seed.a.lead_ids[0],
                uuid.uuid4(),
            )


def test_notification_rows_are_isolated_by_tenant_rls(admin_engine, app_engine, seed):
    notification_ids = {
        "a": uuid.uuid4(),
        "b": uuid.uuid4(),
    }
    for letter in ("a", "b"):
        tenant = seed.get(letter)
        with admin_engine.begin() as conn:
            set_tenant(conn, tenant.id)
            _insert_notification(
                conn,
                tenant.id,
                tenant.users["rep"][0],
                tenant.lead_ids[0],
                notification_ids[letter],
            )

    with app_engine.begin() as conn:
        set_tenant(conn, seed.a.id)
        visible = set(conn.execute(text("SELECT id FROM notifications")).scalars().all())

    assert visible == {notification_ids["a"]}


def test_notification_service_rejects_lead_from_another_tenant(admin_engine, seed):
    tenant = seed.a
    title = f"Cross-tenant {uuid.uuid4()}"
    request, context = _request_and_context(
        tenant,
        seed.b.lead_ids[0],
        f"cross-tenant-{uuid.uuid4().hex}",
        title,
    )

    with Session(admin_engine) as session:
        with pytest.raises(AuthError) as error:
            service.create_notification(session, context, request)

    assert error.value.status_code == 404
    with admin_engine.connect() as conn:
        count = conn.scalar(
            text(
                "SELECT count(*) FROM notifications WHERE tenant_id = :tenant_id AND title = :title"
            ),
            {"tenant_id": tenant.id, "title": title},
        )
    assert count == 0


def _request_and_context(tenant, lead_id, key, title):
    payload = NotificationCreateRequest(
        user_id=tenant.users["rep"][0],
        type="new_lead",
        title=title,
        body="A new lead is assigned to you.",
        entity_type="lead",
        entity_id=lead_id,
    )
    serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
    context = InternalServiceContext(
        service_id="n8n",
        tenant_id=tenant.id,
        idempotency_key=key,
        body_sha256=hashlib.sha256(serialized).hexdigest(),
    )
    return payload, context


def test_concurrent_same_key_creates_one_notification(admin_engine, seed):
    tenant = seed.a
    title = f"Concurrent {uuid.uuid4()}"
    key = f"concurrent-{uuid.uuid4().hex}"
    request, context = _request_and_context(tenant, tenant.lead_ids[0], key, title)
    barrier = Barrier(2)

    def create():
        with Session(admin_engine) as session:
            barrier.wait(timeout=10)
            service.create_notification(session, context, request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)

    with admin_engine.connect() as conn:
        count = conn.scalar(
            text(
                "SELECT count(*) FROM notifications WHERE tenant_id = :tenant_id AND title = :title"
            ),
            {"tenant_id": tenant.id, "title": title},
        )
    assert count == 1


def test_expired_idempotency_key_can_be_reused_after_24_hours(admin_engine, seed):
    tenant = seed.a
    title = f"Expired {uuid.uuid4()}"
    key = f"expired-{uuid.uuid4().hex}"
    request, context = _request_and_context(tenant, tenant.lead_ids[0], key, title)

    with Session(admin_engine) as session:
        service.create_notification(session, context, request)

    with admin_engine.begin() as conn:
        set_tenant(conn, tenant.id)
        conn.execute(
            text(
                "UPDATE idempotency_keys SET expires_at = now() - interval '1 second' "
                "WHERE tenant_id = :tenant_id AND caller_type = 'service' "
                "AND caller_id = 'n8n' AND method = 'POST' "
                "AND path = '/internal/v1/automation/notifications' AND key = :key"
            ),
            {"tenant_id": tenant.id, "key": key},
        )

    with Session(admin_engine) as session:
        service.create_notification(session, context, request)

    with admin_engine.connect() as conn:
        count = conn.scalar(
            text(
                "SELECT count(*) FROM notifications WHERE tenant_id = :tenant_id AND title = :title"
            ),
            {"tenant_id": tenant.id, "title": title},
        )
    assert count == 2
