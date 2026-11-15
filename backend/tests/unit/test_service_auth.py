import asyncio
import uuid

import pytest

from app.core.service_auth import (
    MAX_INTERNAL_BODY_BYTES,
    _read_request_body,
    build_signature,
    canonical_request,
    verify_internal_request,
)
from app.modules.auth.errors import AuthError

SECRET = "test-service-secret"
NOW = 1_800_000_000
TENANT_ID = str(uuid.UUID("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"))
BODY = b'{"type":"new_lead"}'
PATH = "/internal/v1/automation/notifications"


def signed_headers(**overrides):
    headers = {
        "X-Service-Id": "n8n",
        "X-Tenant-ID": TENANT_ID,
        "X-Timestamp": str(NOW),
        "X-Idempotency-Key": "logical-action-123",
    }
    headers.update(overrides)
    canonical = canonical_request(
        service_id=headers["X-Service-Id"],
        tenant_id=headers["X-Tenant-ID"],
        method="POST",
        path=PATH,
        timestamp=headers["X-Timestamp"],
        idempotency_key=headers["X-Idempotency-Key"],
        raw_body=BODY,
    )
    headers["X-Signature"] = build_signature(SECRET, canonical)
    return headers


def test_canonical_request_binds_all_fields_in_v1_order():
    canonical = canonical_request(
        service_id="n8n",
        tenant_id=TENANT_ID,
        method="post",
        path=PATH,
        timestamp=str(NOW),
        idempotency_key="logical-action-123",
        raw_body=BODY,
    )

    assert canonical.decode() == (
        "v1\n"
        f"n8n\n{TENANT_ID}\nPOST\n{PATH}\n{NOW}\n"
        "logical-action-123\n"
        "cf343cbc544096b599d346e2cc918512a6b2a31be330febb5d1f5916a068808d"
    )


def test_valid_signature_returns_authenticated_context():
    context = verify_internal_request(
        signed_headers(),
        method="POST",
        path=PATH,
        raw_body=BODY,
        secret=SECRET,
        now=NOW,
    )

    assert context.service_id == "n8n"
    assert context.tenant_id == uuid.UUID(TENANT_ID)
    assert context.idempotency_key == "logical-action-123"


@pytest.mark.parametrize(
    "header,value",
    [
        ("X-Service-Id", "other-service"),
        ("X-Tenant-ID", str(uuid.uuid4())),
        ("X-Idempotency-Key", "different-action-123"),
    ],
)
def test_tampered_signed_headers_are_rejected(header, value):
    headers = signed_headers()
    headers[header] = value
    with pytest.raises(AuthError) as error:
        verify_internal_request(
            headers,
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )

    assert error.value.status_code == 401


def test_body_modification_is_rejected():
    with pytest.raises(AuthError):
        verify_internal_request(
            signed_headers(),
            method="POST",
            path=PATH,
            raw_body=b'{"type":"changed"}',
            secret=SECRET,
            now=NOW,
        )


def test_path_and_method_are_signed():
    headers = signed_headers()

    with pytest.raises(AuthError):
        verify_internal_request(
            headers,
            method="POST",
            path=f"{PATH}?extra=true",
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )

    with pytest.raises(AuthError):
        verify_internal_request(
            headers,
            method="PUT",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )


def test_timestamp_tolerance_and_malformed_header_are_enforced():
    with pytest.raises(AuthError) as expired:
        verify_internal_request(
            signed_headers(),
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW + 301,
        )
    assert expired.value.status_code == 401

    assert verify_internal_request(
        signed_headers(),
        method="POST",
        path=PATH,
        raw_body=BODY,
        secret=SECRET,
        now=NOW + 300,
    ).tenant_id == uuid.UUID(TENANT_ID)

    with pytest.raises(AuthError):
        headers = signed_headers()
        headers["X-Idempotency-Key"] = "bad\nkey"
        verify_internal_request(
            headers,
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )

    headers = signed_headers()
    headers["X-Signature"] = "sha256=invalid"
    with pytest.raises(AuthError):
        verify_internal_request(
            headers,
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )


def test_missing_header_empty_secret_and_unsupported_service_fail_closed():
    headers = signed_headers()
    headers.pop("X-Timestamp")
    with pytest.raises(AuthError):
        verify_internal_request(
            headers,
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )

    with pytest.raises(AuthError) as missing_secret:
        verify_internal_request(
            signed_headers(),
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret="",
            now=NOW,
        )
    assert missing_secret.value.status_code == 503

    headers = signed_headers(**{"X-Service-Id": "unknown"})
    with pytest.raises(AuthError) as unsupported:
        verify_internal_request(
            headers,
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )
    assert unsupported.value.status_code == 401


def test_noncanonical_tenant_uuid_is_rejected():
    with pytest.raises(AuthError):
        verify_internal_request(
            signed_headers(**{"X-Tenant-ID": TENANT_ID.upper()}),
            method="POST",
            path=PATH,
            raw_body=BODY,
            secret=SECRET,
            now=NOW,
        )


def test_internal_request_body_limit_covers_streamed_and_declared_sizes():
    class FakeRequest:
        def __init__(self, chunks, headers=()):
            self.chunks = chunks
            self.scope = {"headers": list(headers)}

        async def stream(self):
            for chunk in self.chunks:
                yield chunk

    declared_too_large = FakeRequest(
        [],
        [(b"content-length", str(MAX_INTERNAL_BODY_BYTES + 1).encode())],
    )
    with pytest.raises(AuthError) as declared_error:
        asyncio.run(_read_request_body(declared_too_large))
    assert declared_error.value.status_code == 413

    streamed_too_large = FakeRequest([b"x" * MAX_INTERNAL_BODY_BYTES, b"x"])
    with pytest.raises(AuthError) as streamed_error:
        asyncio.run(_read_request_body(streamed_too_large))
    assert streamed_error.value.status_code == 413
