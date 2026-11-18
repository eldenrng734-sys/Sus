"""Golden vector test for internal service authentication.

This exact test vector is documented in n8n/README.md and verified
by both simulate_n8n.py and n8n sub-workflow sign-and-call.
"""

from app.core.service_auth import (
    build_signature,
    canonical_request,
    verify_internal_request,
)

GOLDEN_SECRET = "test-golden-service-secret-key-12345"
GOLDEN_SERVICE_ID = "n8n"
GOLDEN_TENANT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
GOLDEN_METHOD = "POST"
GOLDEN_PATH = "/internal/v1/automation/notifications"
GOLDEN_TIMESTAMP = "1700000000"
GOLDEN_IDEMPOTENCY_KEY = "golden-idempotency-key-001"
GOLDEN_RAW_BODY = b'{"type":"new_lead","title":"New lead"}'

GOLDEN_BODY_SHA256 = "9636ffd5118576eb56cc29efa63d5f1d184fd6e063cc29cdbefacff8ba77fe19"
GOLDEN_SIGNATURE = "sha256=f24f7a152e7388f25a0eda7f17e298dfbbc58177ca54a8fa5180c3a603602ef6"


def test_golden_vector_canonical_request():
    canonical = canonical_request(
        service_id=GOLDEN_SERVICE_ID,
        tenant_id=GOLDEN_TENANT_ID,
        method=GOLDEN_METHOD,
        path=GOLDEN_PATH,
        timestamp=GOLDEN_TIMESTAMP,
        idempotency_key=GOLDEN_IDEMPOTENCY_KEY,
        raw_body=GOLDEN_RAW_BODY,
    )
    expected_canonical = (
        b"v1\n"
        b"n8n\n"
        b"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d\n"
        b"POST\n"
        b"/internal/v1/automation/notifications\n"
        b"1700000000\n"
        b"golden-idempotency-key-001\n"
        b"9636ffd5118576eb56cc29efa63d5f1d184fd6e063cc29cdbefacff8ba77fe19"
    )
    assert canonical == expected_canonical


def test_golden_vector_signature():
    canonical = canonical_request(
        service_id=GOLDEN_SERVICE_ID,
        tenant_id=GOLDEN_TENANT_ID,
        method=GOLDEN_METHOD,
        path=GOLDEN_PATH,
        timestamp=GOLDEN_TIMESTAMP,
        idempotency_key=GOLDEN_IDEMPOTENCY_KEY,
        raw_body=GOLDEN_RAW_BODY,
    )
    sig = build_signature(GOLDEN_SECRET, canonical)
    assert sig == GOLDEN_SIGNATURE


def test_golden_vector_verification():
    headers = {
        "X-Service-Id": GOLDEN_SERVICE_ID,
        "X-Tenant-ID": GOLDEN_TENANT_ID,
        "X-Timestamp": GOLDEN_TIMESTAMP,
        "X-Idempotency-Key": GOLDEN_IDEMPOTENCY_KEY,
        "X-Signature": GOLDEN_SIGNATURE,
    }
    context = verify_internal_request(
        headers,
        method=GOLDEN_METHOD,
        path=GOLDEN_PATH,
        raw_body=GOLDEN_RAW_BODY,
        secret=GOLDEN_SECRET,
        now=int(GOLDEN_TIMESTAMP),
    )
    assert context.service_id == GOLDEN_SERVICE_ID
    assert str(context.tenant_id) == GOLDEN_TENANT_ID
    assert context.idempotency_key == GOLDEN_IDEMPOTENCY_KEY
    assert context.body_sha256 == GOLDEN_BODY_SHA256
