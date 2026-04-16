"""LLM client using httpx for OpenAI-compatible Chat Completions API.

No SDK dependency — raw HTTP calls to localhost LLM endpoints.
Integrates nlk for prompt injection defense, JSON repair, retry, and output cleaning.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol, runtime_checkable

import httpx
from nlk.backoff import duration as backoff_duration
from nlk.jsonfix import NoJsonError, UnfixableError, extract_to
from nlk.strip import think_tags

from cti_primer.config import LLMConfig

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 5


class LLMError(Exception):
    """Raised when LLM call fails after retries."""


class LLMJsonError(LLMError):
    """Raised when LLM response cannot be parsed as JSON."""


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM clients — enables dependency injection and testing."""

    def complete(self, system: str, user: str) -> str: ...

    def complete_json(self, system: str, user: str) -> Any: ...


class HttpxLLMClient:
    """httpx-based client for OpenAI-compatible Chat Completions API.

    Uses nlk utilities for:
      - strip.think_tags: remove model thinking/reasoning
      - jsonfix.extract_to: extract and repair JSON from responses
      - backoff.duration: exponential backoff for retries
    """

    def __init__(
        self,
        config: LLMConfig,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._http = http_client or httpx.Client(timeout=config.timeout)
        self._endpoint = config.endpoint.rstrip("/") + "/chat/completions"

    def complete(self, system: str, user: str) -> str:
        """Send chat completion and return cleaned text response."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = self._send_request(messages)
        return think_tags(raw).strip()

    def complete_json(self, system: str, user: str) -> Any:
        """Send chat completion and return parsed JSON.

        Uses nlk.strip.think_tags + nlk.jsonfix.extract_to for robust parsing.

        Raises:
            LLMJsonError: If response cannot be parsed as valid JSON.
        """
        raw_text = self.complete(system, user)
        try:
            return extract_to(raw_text)
        except (NoJsonError, UnfixableError) as exc:
            raise LLMJsonError(f"Failed to extract JSON from LLM response: {exc}") from exc

    def _send_request(self, messages: list[dict[str, str]]) -> str:
        """POST to /chat/completions with retry on transient errors."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._config.api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
        }

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._http.post(
                    self._endpoint,
                    json=body,
                    headers=headers,
                )
                if resp.status_code in _RETRYABLE_STATUS:
                    logger.warning(
                        "LLM request returned %d (attempt %d/%d)",
                        resp.status_code,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    last_error = LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(backoff_duration(attempt, base=2.0, max_delay=60.0))
                    continue

                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

            except httpx.TimeoutException as exc:
                logger.warning(
                    "LLM request timed out (attempt %d/%d)",
                    attempt + 1,
                    _MAX_RETRIES,
                )
                last_error = exc
                time.sleep(backoff_duration(attempt, base=2.0, max_delay=60.0))

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _RETRYABLE_STATUS:
                    logger.warning(
                        "LLM request HTTP error %d (attempt %d/%d)",
                        exc.response.status_code,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    last_error = exc
                    time.sleep(backoff_duration(attempt, base=2.0, max_delay=60.0))
                    continue
                raise LLMError(f"Non-retryable HTTP error {exc.response.status_code}") from exc

        raise LLMError(f"LLM request failed after {_MAX_RETRIES} attempts") from last_error

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()


class NoLLMClient:
    """Stub client for --no-llm mode. Raises on any call."""

    def complete(self, system: str, user: str) -> str:
        raise LLMError("LLM is not available in --no-llm mode. This operation requires LLM support.")

    def complete_json(self, system: str, user: str) -> Any:
        raise LLMError("LLM is not available in --no-llm mode. This operation requires LLM support.")
