"""Unit tests for simulation scripts (simulate_n8n and simulate_whatsapp)."""

import json
import uuid
from unittest.mock import MagicMock, patch

from scripts.simulate_n8n import (
    run_workflow_a,
    run_workflow_b,
    run_workflow_c,
    sign_request,
    verify_golden_vector,
)
from scripts.simulate_whatsapp import (
    build_whatsapp_inbound_payload,
    post_inbound_message,
)


def test_simulate_n8n_golden_vector():
    assert verify_golden_vector() is True


def test_simulate_n8n_sign_request():
    raw_body, headers = sign_request(
        secret="my-test-secret",
        tenant_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
        method="POST",
        path="/internal/v1/automation/messages",
        idempotency_key="key-12345",
        body={"hello": "world"},
        timestamp="1700000000",
    )
    assert headers["X-Service-Id"] == "n8n"
    assert headers["X-Tenant-ID"] == "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    assert headers["X-Timestamp"] == "1700000000"
    assert headers["X-Idempotency-Key"] == "key-12345"
    assert headers["X-Signature"].startswith("sha256=")
    assert json.loads(raw_body.decode()) == {"hello": "world"}


def test_simulate_n8n_run_workflow_a_flow():
    lead_id = "11111111-2222-3333-4444-555555555555"
    tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    assigned_user = "88888888-9999-0000-1111-222222222222"

    api_calls = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        api_calls.append((method, path, idempotency_key))
        if path.startswith("/internal/v1/automation/leads/") and method == "GET":
            return {
                "status_code": 200,
                "data": {
                    "data": {
                        "id": lead_id,
                        "name": "Test Lead",
                        "status": "new",
                        "assigned_user_id": assigned_user,
                    }
                },
            }
        elif path.endswith("/assess") and method == "POST":
            return {"status_code": 202, "data": {"status": "requested"}}
        elif path == "/internal/v1/automation/notifications" and method == "POST":
            return {"status_code": 202, "data": {}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_a(
            "http://test:8000",
            "secret-123",
            tenant_id=tenant_id,
            lead_id=lead_id,
            event_id="event-abc",
        )
        assert res["status"] == "completed"
        # 3 calls: GET lead, POST assess, POST notification
        assert len(api_calls) == 3
        expected_lead_path = f"/internal/v1/automation/leads/{lead_id}"
        expected_assess_path = f"/internal/v1/automation/leads/{lead_id}/assess"
        assert api_calls[0] == ("GET", expected_lead_path, "event-abc-get-lead")
        assert api_calls[1] == ("POST", expected_assess_path, "event-abc-assess")
        assert api_calls[2] == ("POST", "/internal/v1/automation/notifications", "event-abc")


def test_simulate_whatsapp_payload_structure():
    payload = build_whatsapp_inbound_payload(
        phone_number_id="pn_123",
        sender_phone="+8801700000000",
        sender_name="Karim",
        message_text="Interested in pricing",
    )
    assert payload["object"] == "whatsapp_business_account"
    entry = payload["entry"][0]
    change = entry["changes"][0]["value"]
    assert change["metadata"]["phone_number_id"] == "pn_123"
    assert change["contacts"][0]["profile"]["name"] == "Karim"
    assert change["contacts"][0]["wa_id"] == "8801700000000"
    assert change["messages"][0]["text"]["body"] == "Interested in pricing"


def test_simulate_whatsapp_post_mock():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"status":"ok"}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = post_inbound_message(
            "http://test:8000/api/v1/webhooks/whatsapp",
            "meta-secret",
            phone_number_id="pn_123",
            sender_phone="+8801700000000",
            sender_name="Karim",
            message_text="Pricing info",
        )
        assert res["status_code"] == 200
        assert res["data"] == {"status": "ok"}


def test_workflow_b_opted_out_lead_never_receives_follow_up():
    task_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    tenant_id = "11111111-2222-3333-4444-555555555555"

    recorded = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        if path == "/internal/v1/automation/messages":
            # Opted out returns 409
            return {
                "status_code": 409,
                "error": {"code": "opted_out", "message": "Lead opted out"},
            }
        elif "/tasks/" in path and path.endswith("/result"):
            recorded.append(body)
            return {"status_code": 200, "data": {}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_b(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            task_id=task_id,
            event_id="ev-optout",
        )
        assert res["outcome"] == "opted_out"
        assert len(recorded) == 1
        assert recorded[0]["status"] == "skipped"
        assert recorded[0]["task_status"] == "cancelled"
        assert recorded[0]["error_code"] == "opted_out"


def test_workflow_b_stale_task_due_for_paused_task_is_skipped():
    task_id = "paused-task-uuid"
    tenant_id = "11111111-2222-3333-4444-555555555555"

    recorded = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        if path == "/internal/v1/automation/messages":
            # Paused task rejected with task_not_open
            return {
                "status_code": 409,
                "error": {"code": "task_not_open", "message": "Task is paused"},
            }
        elif "/tasks/" in path and path.endswith("/result"):
            recorded.append(body)
            return {"status_code": 200, "data": {}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_b(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            task_id=task_id,
            event_id="ev-paused",
        )
        assert res["outcome"] == "task_not_open"
        assert len(recorded) == 1
        assert recorded[0]["status"] == "skipped"
        assert recorded[0]["error_code"] == "task_not_open"


def test_workflow_b_sent_success():
    task_id = "open-task-uuid"
    tenant_id = "11111111-2222-3333-4444-555555555555"

    recorded = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        if path == "/internal/v1/automation/messages":
            return {
                "status_code": 200,
                "data": {"data": {"status": "sent", "message_id": "msg-123"}},
            }
        elif "/tasks/" in path and path.endswith("/result"):
            recorded.append(body)
            return {"status_code": 200, "data": {}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_b(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            task_id=task_id,
            event_id="ev-sent",
        )
        assert res["outcome"] == "sent"
        assert len(recorded) == 1
        assert recorded[0]["status"] == "sent"
        assert recorded[0]["task_status"] == "done"
        assert recorded[0]["message_id"] == "msg-123"


def test_workflow_b_quiet_hours_reschedule():
    task_id = "quiet-task-uuid"
    tenant_id = "11111111-2222-3333-4444-555555555555"

    recorded = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        if path == "/internal/v1/automation/messages":
            return {
                "status_code": 202,
                "data": {"data": {"status": "rescheduled", "reason": "quiet_hours"}},
            }
        elif "/tasks/" in path and path.endswith("/result"):
            recorded.append(body)
            return {"status_code": 200, "data": {}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_b(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            task_id=task_id,
            event_id="ev-quiet",
        )
        assert res["outcome"] == "quiet_hours"
        # Quiet hours is already rescheduled by backend: nothing recorded to tasks result
        assert len(recorded) == 0


def test_workflow_c_with_assigned_rep():
    lead_id = "22222222-3333-4444-5555-666666666666"
    tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    assigned_user = "99999999-0000-1111-2222-333333333333"

    api_calls = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        api_calls.append((method, path, idempotency_key, body))
        if path.startswith("/internal/v1/automation/leads/") and method == "GET":
            return {
                "status_code": 200,
                "data": {
                    "data": {
                        "id": lead_id,
                        "name": "Replied Lead",
                        "status": "contacted",
                        "assigned_user_id": assigned_user,
                    }
                },
            }
        elif path == "/internal/v1/automation/notifications" and method == "POST":
            return {"status_code": 202, "data": {}}
        elif path.endswith("/assess") and method == "POST":
            return {"status_code": 200, "data": {"data": {"status": "satisfied"}}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_c(
            "http://test:8000",
            "secret-123",
            tenant_id=tenant_id,
            lead_id=lead_id,
            event_id="reply-event-1",
        )
        assert res["status"] == "completed"
        # 3 calls: GET lead, POST notification, POST assess
        assert len(api_calls) == 3
        assert api_calls[0][0] == "GET"
        assert api_calls[0][1] == f"/internal/v1/automation/leads/{lead_id}"
        assert api_calls[0][2] == "reply-event-1-get-lead"

        assert api_calls[1][0] == "POST"
        assert api_calls[1][1] == "/internal/v1/automation/notifications"
        assert api_calls[1][2] == "reply-event-1-notif"
        assert api_calls[1][3]["user_id"] == assigned_user
        assert api_calls[1][3]["type"] == "new_lead"
        assert "Replied Lead" in api_calls[1][3]["title"]

        assert api_calls[2][0] == "POST"
        assert api_calls[2][1] == f"/internal/v1/automation/leads/{lead_id}/assess"
        assert api_calls[2][2] == "reply-event-1-assess"


def test_workflow_c_unassigned_lead_skips_notification():
    lead_id = "33333333-4444-5555-6666-777777777777"
    tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"

    api_calls = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        api_calls.append((method, path, idempotency_key))
        if path.startswith("/internal/v1/automation/leads/") and method == "GET":
            return {
                "status_code": 200,
                "data": {
                    "data": {
                        "id": lead_id,
                        "name": "Unassigned Lead",
                        "status": "new",
                        "assigned_user_id": None,
                    }
                },
            }
        elif path.endswith("/assess") and method == "POST":
            return {"status_code": 202, "data": {"data": {"status": "requested"}}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_c(
            "http://test:8000",
            "secret-123",
            tenant_id=tenant_id,
            lead_id=lead_id,
            event_id="reply-event-2",
        )
        assert res["status"] == "completed"
        # 2 calls: GET lead and POST assess (notification skipped because no assigned rep)
        assert len(api_calls) == 2
        expected_lead = f"/internal/v1/automation/leads/{lead_id}"
        expected_assess = f"/internal/v1/automation/leads/{lead_id}/assess"
        assert api_calls[0] == ("GET", expected_lead, "reply-event-2-get-lead")
        assert api_calls[1] == ("POST", expected_assess, "reply-event-2-assess")
        assert res["notification"] is None


def test_workflow_c_unassigned_lead_notifies_team_managers():
    lead_id = "33333333-4444-5555-6666-777777777777"
    tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    mgr1 = "aaaaaaaa-1111-2222-3333-444444444444"
    mgr2 = "bbbbbbbb-1111-2222-3333-444444444444"

    api_calls = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        api_calls.append((method, path, idempotency_key, body))
        if path.startswith("/internal/v1/automation/leads/") and method == "GET":
            return {
                "status_code": 200,
                "data": {
                    "data": {
                        "id": lead_id,
                        "name": "Unassigned Lead",
                        "status": "new",
                        "assigned_user_id": None,
                        "manager_user_ids": [mgr1, mgr2],
                    }
                },
            }
        elif path == "/internal/v1/automation/notifications" and method == "POST":
            return {"status_code": 202, "data": {}}
        elif path.endswith("/assess") and method == "POST":
            return {"status_code": 202, "data": {"data": {"status": "requested"}}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_c(
            "http://test:8000",
            "secret-123",
            tenant_id=tenant_id,
            lead_id=lead_id,
            event_id="reply-event-mgr",
        )
        assert res["status"] == "completed"
        # 4 calls: GET lead, 2 POST notifications (for each manager), 1 POST assess
        assert len(api_calls) == 4
        assert api_calls[0][0] == "GET"
        assert api_calls[1][0] == "POST"
        assert api_calls[1][1] == "/internal/v1/automation/notifications"
        assert api_calls[1][3]["user_id"] == mgr1
        assert api_calls[2][0] == "POST"
        assert api_calls[2][1] == "/internal/v1/automation/notifications"
        assert api_calls[2][3]["user_id"] == mgr2
        assert api_calls[3][0] == "POST"
        assert api_calls[3][1] == f"/internal/v1/automation/leads/{lead_id}/assess"


def test_simulate_n8n_down_goes_dead_after_5_attempts():
    """Verify that when n8n is down, dispatcher retries until attempts reach 5, then goes dead."""
    from types import SimpleNamespace

    from app.core.dispatcher import ClaimedDispatcherEvent, process_event

    event = ClaimedDispatcherEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event_type="lead.created",
        aggregate_type="lead",
        aggregate_id=uuid.uuid4(),
        payload={"lead_id": str(uuid.uuid4())},
        attempts=5,
    )

    calls = []

    class MockSession:
        def execute(self, stmt, params=None):
            calls.append((str(stmt), params))
            return SimpleNamespace(all=lambda: [], first=lambda: None)

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    class DownClient:
        def post(self, url, headers=None, content=None, timeout=None):
            return SimpleNamespace(status_code=503, is_success=False)

    outcome = process_event(
        lambda: MockSession(),
        event,
        webhook_url="http://n8n:5678/webhook",
        signing_secret="secret",
        http_client=DownClient(),
    )

    assert outcome == "dead"
    dead_update = next(p for stmt, p in calls if "UPDATE outbox_events" in stmt)
    assert dead_update["s"] == "dead"
    assert dead_update["e"] == "DeliveryError"


def test_simulate_n8n_replays_deduplicated_by_backend():
    """When n8n redelivers with the same event ID, calls are deduplicated."""
    lead_id = "44444444-5555-6666-7777-888888888888"
    tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"

    seen_keys = set()
    replay_count = 0

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        nonlocal replay_count
        if idempotency_key in seen_keys:
            replay_count += 1
            return {"status_code": 200, "data": {"data": {"replayed": True}}}
        seen_keys.add(idempotency_key)
        return {"status_code": 200, "data": {"data": {"id": lead_id, "name": "Lead"}}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        # First execution
        res1 = run_workflow_a(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            lead_id=lead_id,
            event_id="stable-event-id",
        )
        assert res1["status"] == "completed"

        # Redelivery of same event ID
        res2 = run_workflow_a(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            lead_id=lead_id,
            event_id="stable-event-id",
        )
        assert res2["status"] == "completed"
        # All calls in second run were recognized as replays
        assert replay_count >= 1


def test_simulate_internal_api_401_recorded_without_payload():
    """A 401 rejection from the internal API is recorded with only error_code,
    zero message payload.
    """
    task_id = "55555555-6666-7777-8888-999999999999"
    tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"

    recorded = []

    def mock_call_api(base_url, secret, *, tenant_id, method, path, idempotency_key, body=None):
        if path == "/internal/v1/automation/messages":
            return {
                "status_code": 401,
                "error": {"code": "unauthorized", "message": "Invalid HMAC signature"},
            }
        elif "/tasks/" in path and path.endswith("/result"):
            recorded.append(body)
            return {"status_code": 200, "data": {}}
        return {"status_code": 200, "data": {}}

    with patch("scripts.simulate_n8n.call_internal_api", side_effect=mock_call_api):
        res = run_workflow_b(
            "http://test:8000",
            "secret",
            tenant_id=tenant_id,
            task_id=task_id,
            event_id="ev-401",
        )
        assert res["outcome"] == "failed"
        assert len(recorded) == 1
        assert recorded[0]["status"] == "failed"
        assert recorded[0]["error_code"] == "unauthorized"
        # Never records raw message text or tokens
        assert "message_text" not in recorded[0]
        assert "payload" not in recorded[0]
