"""Meta webhook signature verification.

This module is the SINGLE place where HMAC code lives for all Meta webhooks.
WhatsApp, Messenger, and Lead Ads all use the same scheme:
  - Header:    X-Hub-Signature-256
  - Algorithm: HMAC-SHA256 of the raw (unparsed) request body
  - Key:       Meta app secret (settings.meta_app_secret)
  - Format:    "sha256=<hex-digest>"

No other module in this codebase should import hashlib or hmac for
webhook signature purposes.  Providers call verify_signature() here.
"""

import hashlib
import hmac


def build_signature(raw_body: bytes, app_secret: str) -> str:
    """Generate the expected HMAC-SHA256 signature for a webhook body.

    Returns "" when app_secret is empty so callers can detect misconfiguration
    without crashing.  An empty return value will always fail verify_signature.
    """
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
    """Return True only when the HMAC-SHA256 signature is valid.

    Args:
        raw_body:   The raw, unmodified request body bytes.  Must be read
                    before any JSON parsing; parsing may normalise whitespace
                    and invalidate the signature.
        signature:  The value of the X-Hub-Signature-256 header, e.g.
                    "sha256=abc123...".  None or "" → always False.
        app_secret: The Meta app secret.  Pass
                    settings.meta_app_secret.get_secret_value() at the call
                    site; never log or store this value.

    Returns False (never raises) on any input that cannot be verified, so
    the caller can safely convert the return value directly to an HTTP 401.

    Uses hmac.compare_digest to prevent timing-oracle attacks.
    """
    if not app_secret or not signature:
        return False

    expected = build_signature(raw_body, app_secret)
    return hmac.compare_digest(expected, signature.strip())
