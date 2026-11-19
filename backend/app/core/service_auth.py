import hashlib
import hmac
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import Request

from app.core.config import settings
from app.modules.auth.errors import AuthError

SERVICE_ID = "n8n"
SIGNATURE_PREFIX = "sha256="
TIMESTAMP_TOLERANCE_SECONDS = 300
MAX_INTERNAL_BODY_BYTES = 16 * 1024
_SIGNATURE_PATTERN = re.compile(r"sha256=[0-9a-f]{64}\Z")
_TIMESTAMP_PATTERN = re.compile(r"[0-9]{1,12}\Z")


@dataclass(frozen=True)
class InternalServiceContext:
    service_id: str
    tenant_id: uuid.UUID
    idempotency_key: str
    body_sha256: str


def canonical_request(
    *,
    service_id: str,
    tenant_id: str,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    raw_body: bytes,
) -> bytes:
    fields = (
        "v1",
        service_id,
        tenant_id,
        method.upper(),
        path,
        timestamp,
        idempotency_key,
        hashlib.sha256(raw_body).hexdigest(),
    )
    if any("\r" in value or "\n" in value for value in fields):
        raise ValueError("Canonical fields cannot contain line breaks")
    return "\n".join(fields).encode("utf-8")


def build_signature(secret: str, canonical: bytes) -> str:
    if not secret:
        raise ValueError("A service secret is required")
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_internal_request(
    headers: Mapping[str, str],
    *,
    method: str,
    path: str,
    raw_body: bytes,
    secret: str | None,
    now: int | None = None,
) -> InternalServiceContext:
    service_id = _header(headers, "X-Service-Id")
    tenant_header = _header(headers, "X-Tenant-ID")
    timestamp = _header(headers, "X-Timestamp")
    idempotency_key = _header(headers, "X-Idempotency-Key")
    signature = _header(headers, "X-Signature")

    if service_id != SERVICE_ID:
        raise _authentication_error()
    if not secret:
        raise AuthError(
            503,
            "service_unavailable",
            "Internal service authentication is not configured",
        )
    if not _TIMESTAMP_PATTERN.fullmatch(timestamp):
        raise _authentication_error()
    if not 8 <= len(idempotency_key) <= 128:
        raise _authentication_error()
    if not _SIGNATURE_PATTERN.fullmatch(signature):
        raise _authentication_error()

    timestamp_value = int(timestamp)
    if str(timestamp_value) != timestamp:
        raise _authentication_error()
    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp_value) > TIMESTAMP_TOLERANCE_SECONDS:
        raise _authentication_error()

    try:
        tenant_id = uuid.UUID(tenant_header)
        if str(tenant_id) != tenant_header:
            raise ValueError("Tenant ID must use canonical UUID syntax")
        canonical = canonical_request(
            service_id=service_id,
            tenant_id=tenant_header,
            method=method,
            path=path,
            timestamp=timestamp,
            idempotency_key=idempotency_key,
            raw_body=raw_body,
        )
    except (ValueError, AttributeError) as exc:
        raise _authentication_error() from exc

    expected_signature = build_signature(secret, canonical)
    if not hmac.compare_digest(signature, expected_signature):
        raise _authentication_error()

    return InternalServiceContext(
        service_id=service_id,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        body_sha256=hashlib.sha256(raw_body).hexdigest(),
    )


def _header(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name)
    if not value or value != value.strip() or "\r" in value or "\n" in value:
        raise _authentication_error()
    return value


def _request_path(request: Request) -> str:
    raw_path = request.scope.get("raw_path")
    if not isinstance(raw_path, bytes):
        raise _authentication_error()
    query_string = request.scope.get("query_string", b"")
    if not isinstance(query_string, bytes):
        raise _authentication_error()
    try:
        path = raw_path.decode("ascii")
        if query_string:
            path = f"{path}?{query_string.decode('ascii')}"
    except UnicodeDecodeError as exc:
        raise _authentication_error() from exc
    return path


def _request_headers(request: Request) -> dict[str, str]:
    required = {
        "x-service-id": "X-Service-Id",
        "x-tenant-id": "X-Tenant-ID",
        "x-timestamp": "X-Timestamp",
        "x-idempotency-key": "X-Idempotency-Key",
        "x-signature": "X-Signature",
    }
    result: dict[str, str] = {}
    for lower_name, name in required.items():
        values = [
            value.decode("latin-1")
            for key, value in request.scope.get("headers", [])
            if key.lower() == lower_name.encode("ascii")
        ]
        if len(values) != 1:
            raise _authentication_error()
        result[name] = values[0]
    return result


async def require_internal_service(request: Request) -> InternalServiceContext:
    raw_body = await _read_request_body(request)
    headers = _request_headers(request)
    secret = (
        settings.n8n_service_secret
        if settings.n8n_service_secret is not None
        else settings.service_hmac_secret
    )
    request.state.internal_raw_body = raw_body
    return verify_internal_request(
        headers,
        method=getattr(request, "method", "POST"),
        path=_request_path(request),
        raw_body=raw_body,
        secret=secret.get_secret_value() if secret is not None else None,
    )


async def _read_request_body(request: Request) -> bytes:
    if getattr(request, "method", "POST") in ("GET", "HEAD"):
        return b""

    content_lengths = [
        value for key, value in request.scope.get("headers", []) if key.lower() == b"content-length"
    ]
    if len(content_lengths) > 1:
        raise AuthError(400, "bad_request", "Invalid Content-Length")
    if content_lengths:
        try:
            declared_length = content_lengths[0].decode("ascii")
            if not declared_length.isdigit():
                raise ValueError("Content-Length must be a non-negative integer")
        except (UnicodeDecodeError, ValueError) as exc:
            raise AuthError(400, "bad_request", "Invalid Content-Length") from exc
        if int(declared_length) == 0:
            return b""
        if int(declared_length) > MAX_INTERNAL_BODY_BYTES:
            raise _body_too_large()

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_INTERNAL_BODY_BYTES:
            raise _body_too_large()
        body.extend(chunk)
    return bytes(body)


def _body_too_large() -> AuthError:
    return AuthError(413, "payload_too_large", "Request body is too large")


def _authentication_error() -> AuthError:
    return AuthError(401, "unauthorized", "Invalid internal service authentication")
