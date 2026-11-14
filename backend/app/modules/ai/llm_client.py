"""Thin, safe wrapper around the hosted LLM API.

Rules (ARCHITECTURE.md section 8): the model gets no tools and no database access,
the caller redacts PII first, and nothing in here ever logs prompt or answer text.
"""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.core.config import settings

logger = logging.getLogger("app.llm")

ANTHROPIC_VERSION = "2023-06-01"
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_INPUT_CHARS = 20_000
MAX_RETRY_AFTER_SECONDS = 10.0


class LLMError(Exception):
    """Base error. Messages never contain prompt text, answer text or keys."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LLMNotConfigured(LLMError):
    """No API key or model is set."""


class LLMTimeout(LLMError):
    """The provider did not answer in time (after all retries)."""


class LLMUnavailable(LLMError):
    """Network error, rate limit or provider overload (after all retries)."""


class LLMRejected(LLMError):
    """A permanent refusal (bad key, bad request). Retrying will not help."""


class LLMBadResponse(LLMError):
    """The provider answered, but not in a shape we can use."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int
    cost_usd: float | None
    truncated: bool


def _backoff_seconds(attempt: int) -> float:
    """Wait 0.5s, 1s, 2s... (max 8s) with jitter, so retries don't all hit at once."""
    return min(8.0, 0.5 * 2 ** (attempt - 1)) * random.uniform(0.5, 1.0)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    try:
        return min(float(raw), MAX_RETRY_AFTER_SECONDS) if raw else None
    except ValueError:
        return None


def _error_type(response: httpx.Response) -> str | None:
    """The provider's short error label (for example 'rate_limit_error'), if any."""
    try:
        return str(response.json()["error"]["type"])
    except (ValueError, KeyError, TypeError):
        return None


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        input_price_per_mtok: float | None = None,
        output_price_per_mtok: float | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = settings.llm_api_key if api_key is None else api_key
        self.model = settings.llm_model if model is None else model
        self.base_url = base_url or settings.llm_base_url
        self.timeout = settings.llm_timeout_seconds if timeout is None else timeout
        self.max_retries = settings.llm_max_retries if max_retries is None else max_retries
        self.input_price = (
            settings.llm_input_price_per_mtok
            if input_price_per_mtok is None
            else input_price_per_mtok
        )
        self.output_price = (
            settings.llm_output_price_per_mtok
            if output_price_per_mtok is None
            else output_price_per_mtok
        )
        self._http = http or httpx.Client(timeout=httpx.Timeout(self.timeout))
        self._sleep = sleep

    def complete(
        self,
        *,
        system: str,
        user: str,
        purpose: str,
        max_tokens: int = 512,
        temperature: float | None = None,
    ) -> LLMResult:
        if not self.api_key or not self.model:
            raise LLMNotConfigured("LLM_API_KEY and LLM_MODEL must be set")
        if len(system) + len(user) > MAX_INPUT_CHARS:
            raise LLMRejected("Prompt is too long")

        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if temperature is not None:  # some models reject sampling settings, so omit by default
            body["temperature"] = temperature
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        started = time.monotonic()
        last_error: LLMError | None = None
        attempt = 0
        for attempt in range(1, self.max_retries + 2):
            retry_after: float | None = None
            try:
                response = self._http.post(self.base_url, headers=headers, json=body)
            except httpx.TimeoutException:
                last_error = LLMTimeout("LLM request timed out")
            except httpx.HTTPError as exc:
                last_error = LLMUnavailable(f"LLM network error ({type(exc).__name__})")
            else:
                if response.status_code == 200:
                    return self._parse(response, started, attempt, purpose)
                if response.status_code not in RETRY_STATUS:
                    self._log_failure(purpose, attempt, started, response.status_code, response)
                    raise LLMRejected(
                        f"LLM rejected the request (HTTP {response.status_code})",
                        status=response.status_code,
                    )
                last_error = LLMUnavailable(
                    f"LLM temporarily unavailable (HTTP {response.status_code})",
                    status=response.status_code,
                )
                retry_after = _retry_after(response)
            if attempt > self.max_retries:
                break
            self._sleep(retry_after if retry_after is not None else _backoff_seconds(attempt))

        assert last_error is not None
        self._log_failure(
            purpose, attempt, started, last_error.status, None, type(last_error).__name__
        )
        raise last_error

    def _parse(
        self, response: httpx.Response, started: float, attempts: int, purpose: str
    ) -> LLMResult:
        try:
            data = response.json()
            text = "".join(
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            )
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            model = str(data.get("model") or self.model)
            truncated = data.get("stop_reason") == "max_tokens"
        except (ValueError, KeyError, TypeError, AttributeError):
            raise LLMBadResponse("LLM returned an unexpected response shape") from None
        if not text.strip():
            raise LLMBadResponse("LLM returned empty text")

        latency_ms = int((time.monotonic() - started) * 1000)
        cost = self._cost(input_tokens, output_tokens)
        logger.info(
            "llm_call purpose=%s model=%s status=ok attempts=%d input_tokens=%d "
            "output_tokens=%d latency_ms=%d cost_usd=%s truncated=%s",
            purpose,
            model,
            attempts,
            input_tokens,
            output_tokens,
            latency_ms,
            "unknown" if cost is None else f"{cost:.6f}",
            truncated,
        )
        return LLMResult(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            attempts=attempts,
            cost_usd=cost,
            truncated=truncated,
        )

    def _cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.input_price <= 0 and self.output_price <= 0:
            return None  # prices not configured
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000

    def _log_failure(
        self,
        purpose: str,
        attempts: int,
        started: float,
        status: int | None,
        response: httpx.Response | None,
        kind: str = "rejected",
    ) -> None:
        logger.warning(
            "llm_call purpose=%s model=%s status=failed kind=%s http_status=%s error_type=%s "
            "attempts=%d latency_ms=%d",
            purpose,
            self.model,
            kind,
            status,
            _error_type(response) if response is not None else None,
            attempts,
            int((time.monotonic() - started) * 1000),
        )


@lru_cache
def get_llm_client() -> LLMClient:
    """One shared client (and connection pool) per process."""
    return LLMClient()