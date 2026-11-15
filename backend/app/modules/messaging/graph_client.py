"""Meta WhatsApp Cloud API client.

Security rules:
- The bearer token lives only in ``self._headers`` and is never logged.
- Message bodies are PII. Do not log request or response payloads.
- 4xx responses are permanent (except 429): retrying a bad payload wastes quota.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

BASE = "https://graph.facebook.com"

# 408 is deliberately absent: it is still a 4xx and the task forbids retrying
# 4xx responses other than 429.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RetryableError(Exception):
    """A transient provider failure. The caller may retry the same request."""

    def __init__(self, status_code: int | None = None) -> None:
        super().__init__(f"WhatsApp provider temporarily unavailable ({status_code})")
        self.status_code = status_code


class GraphAPIError(Exception):
    """A permanent provider failure. Retrying the same payload will not help."""

    def __init__(self, status_code: int, error_code: str | None = None) -> None:
        super().__init__(f"WhatsApp provider rejected the request ({status_code})")
        self.status_code = status_code
        self.error_code = error_code or f"http_{status_code}"


def _provider_error_code(response: httpx.Response) -> str:
    """Return a short, non-PII provider error label for storage/debugging."""
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return f"http_{response.status_code}"

    if not isinstance(error, dict):
        return f"http_{response.status_code}"

    parts = [
        str(error[key])
        for key in ("code", "error_subcode")
        if isinstance(error.get(key), (int, str)) and str(error[key])
    ]
    return ":".join(parts) or f"http_{response.status_code}"


class GraphClient:
    """Small async wrapper around one WhatsApp phone number."""

    def __init__(self, token: str, phone_number_id: str) -> None:
        if not token:
            raise ValueError("A WhatsApp access token is required")
        if not phone_number_id:
            raise ValueError("A WhatsApp phone_number_id is required")

        version = settings.meta_graph_version or "v21.0"
        self._client = httpx.AsyncClient(
            base_url=f"{BASE}/{version}/{phone_number_id}",
            timeout=settings.meta_graph_timeout_seconds,
        )
        # NOTE: never log self._headers.
        self._headers = {"Authorization": f"Bearer {token}"}

    async def __aenter__(self) -> GraphClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_message(self, to: str, payload: dict[str, Any]) -> str:
        """Send one message and return Meta's provider_message_id.

        ``to`` must be E.164 with a leading '+'. The payload is merged into the
        Graph API request body (for example a ``text`` or ``template`` object).
        """
        if not to.startswith("+") or not to[1:].isdigit():
            raise ValueError("Recipient must be E.164 with a leading '+'")

        try:
            response = await self._client.post(
                "/messages",
                json={"to": to, **payload},
                headers=self._headers,
            )
        except httpx.RequestError as exc:
            # Timeouts and connection failures are transient.
            raise RetryableError() from exc

        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableError(response.status_code)

        if response.status_code >= 400:
            raise GraphAPIError(response.status_code, _provider_error_code(response))

        try:
            return str(response.json()["messages"][0]["id"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise GraphAPIError(response.status_code, "invalid_response") from exc
