import hashlib
import hmac


def build_signature(raw_body: bytes, app_secret: str) -> str:
    """Generate the expected Meta/WhatsApp HMAC-SHA256 signature."""
    if not app_secret:
        return ""

    digest = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return f"sha256={digest}"


def verify_signature(
    raw_body: bytes,
    signature: str | None,
    app_secret: str,
) -> bool:
    """Verify a webhook signature without parsing or modifying its body."""
    if not app_secret or not signature:
        return False

    expected = build_signature(raw_body, app_secret)

    return hmac.compare_digest(expected, signature.strip())
