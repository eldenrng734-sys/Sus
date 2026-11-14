import hashlib
import hmac

from app.modules.integrations.signature import (
    build_signature,
    verify_signature,
)


def test_build_signature_returns_sha256_signature():
    body = b'{"event":"message"}'
    secret = "test-secret"

    expected_digest = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    assert build_signature(body, secret) == f"sha256={expected_digest}"


def test_valid_signature_is_accepted():
    body = b'{"event":"message"}'
    secret = "test-secret"
    signature = build_signature(body, secret)

    assert verify_signature(body, signature, secret) is True


def test_tampered_body_is_rejected():
    original_body = b'{"event":"message"}'
    changed_body = b'{"event":"deleted"}'
    secret = "test-secret"

    signature = build_signature(original_body, secret)

    assert verify_signature(changed_body, signature, secret) is False


def test_missing_signature_or_secret_is_rejected():
    body = b'{"event":"message"}'
    signature = build_signature(body, "test-secret")

    assert verify_signature(body, None, "test-secret") is False
    assert verify_signature(body, "", "test-secret") is False
    assert verify_signature(body, signature, "") is False
    assert build_signature(body, "") == ""
