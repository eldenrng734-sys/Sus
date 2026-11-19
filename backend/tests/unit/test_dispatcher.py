"""Tests for n8n event dispatcher (Missing Parts #8).

Tests:
- Signature format matches canonical string:
  sha256=<hex> of HMAC-SHA256(N8N_EVENT_SIGNING_SECRET, timestamp + '.' + raw_body)
- Body contains only IDs and event type metadata, never PII (no names, emails, phones, message text)
- Successful delivery marks outbox row 'processed'
- Failed delivery retries with exponential backoff
- After MAX_ATTEMPTS (5) failures, event status becomes 'dead' and is never auto-retried
"""

import hashlib
import hmac
import json
import uuid
from types import SimpleNamespace

from app.core.dispatcher import (
    MAX_ATTEMPTS,
    ClaimedDispatcherEvent,
    build_dispatcher_body,
    build_signature,
    process_event,
    verify_signature,
)


def _make_event(attempts: int = 0) -> ClaimedDispatcherEvent:
    return ClaimedDispatcherEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event_type="lead.created",
        aggregate_type="lead",
        aggregate_id=uuid.uuid4(),
        payload={
            "lead_id": str(uuid.uuid4()),
            "source": "website",
            # PII that should be filtered out
            "name": "Should Not Leak",
            "email": "leak@example.com",
            "phone": "+8801700000000",
            "message_text": "Secret customer message",
        },
        attempts=attempts,
    )


class _RecordingSession:
    def __init__(self):
        self.calls = []
        self.committed = 0

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return SimpleNamespace(all=lambda: [], first=lambda: None)

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def test_signature_format_matches_canonical_string():
    """X-Signature must equal sha256=<hex> of HMAC-SHA256(secret, timestamp + '.' + raw_body)."""
    secret = "test-n8n-signing-secret"
    timestamp = "1700000000"
    raw_body = '{"event_id":"123","event_type":"lead.created"}'

    # Reference computation
    canonical = f"{timestamp}.{raw_body}".encode("utf-8")
    expected_digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    expected_sig = f"sha256={expected_digest}"

    actual_sig = build_signature(secret, timestamp, raw_body)
    assert actual_sig == expected_sig

    # Verification helper returns True for matching signature
    assert verify_signature(secret, timestamp, raw_body, actual_sig) is True

    # Tampered body returns False
    assert verify_signature(secret, timestamp, raw_body + "tamper", actual_sig) is False

    # Tampered timestamp returns False
    assert verify_signature(secret, "1700000001", raw_body, actual_sig) is False


def test_dispatcher_body_sanitizes_pii():
    """Body sent to n8n must contain only IDs and event types, never PII or message text."""
    event = _make_event()
    raw_body = build_dispatcher_body(event)
    payload = json.loads(raw_body)

    assert payload["event_id"] == str(event.id)
    assert payload["event_type"] == event.event_type
    assert payload["tenant_id"] == str(event.tenant_id)
    assert payload["aggregate_type"] == event.aggregate_type
    assert payload["aggregate_id"] == str(event.aggregate_id)

    # Verify PII is stripped
    for forbidden_key in ("name", "email", "phone", "message_text"):
        assert forbidden_key not in payload["payload"]
        assert forbidden_key not in raw_body


def test_successful_dispatch_marks_event_processed():
    session = _RecordingSession()

    def session_factory():
        return session

    event = _make_event(attempts=1)

    class FakeClient:
        def post(self, url, headers=None, content=None, timeout=None):
            return SimpleNamespace(status_code=200, is_success=True)

    outcome = process_event(
        session_factory,
        event,
        webhook_url="http://fake-n8n:5678/webhook",
        signing_secret="secret",
        http_client=FakeClient(),
    )

    assert outcome == "processed"
    updates = [params for stmt, params in session.calls if "UPDATE outbox_events" in stmt]
    assert len(updates) == 1
    assert updates[0]["s"] == "processed"
    assert updates[0]["e"] is None


def test_failed_delivery_retries_with_exponential_backoff():
    session = _RecordingSession()

    def session_factory():
        return session

    event = _make_event(attempts=1)

    class FailingClient:
        def post(self, url, headers=None, content=None, timeout=None):
            return SimpleNamespace(status_code=500, is_success=False)

    outcome = process_event(
        session_factory,
        event,
        webhook_url="http://fake-n8n:5678/webhook",
        signing_secret="secret",
        http_client=FailingClient(),
    )

    assert outcome == "retry"
    updates = [params for stmt, params in session.calls if "UPDATE outbox_events" in stmt]
    assert len(updates) == 1
    assert updates[0]["status"] == "pending"
    # Delay for attempt 1 is 30 * 2^0 = 30s
    assert updates[0]["d"] == 30.0
    assert updates[0]["e"] == "DeliveryError"


def test_failed_delivery_goes_dead_after_max_attempts():
    """After MAX_ATTEMPTS (5), event goes dead and is never auto-retried."""
    session = _RecordingSession()

    def session_factory():
        return session

    event = _make_event(attempts=MAX_ATTEMPTS)  # 5th attempt failed

    class FailingClient:
        def post(self, url, headers=None, content=None, timeout=None):
            return SimpleNamespace(status_code=502, is_success=False)

    outcome = process_event(
        session_factory,
        event,
        webhook_url="http://fake-n8n:5678/webhook",
        signing_secret="secret",
        http_client=FailingClient(),
    )

    assert outcome == "dead"
    updates = [params for stmt, params in session.calls if "UPDATE outbox_events" in stmt]
    assert len(updates) == 1
    assert updates[0]["s"] == "dead"
    assert updates[0]["e"] == "DeliveryError"
