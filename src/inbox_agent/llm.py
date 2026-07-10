"""LLM access behind one thin, provider-agnostic interface.

``LLMClient`` is the seam. ``OpenAICompatibleClient`` is the single
implementation: it speaks the OpenAI chat-completions protocol, so Groq,
Gemini, OpenRouter, Ollama and LM Studio are all a ``.env`` change rather than
a code change.

Free tiers are tightly rate-limited, so 429/5xx/timeout responses are expected
and retried with exponential backoff.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TypeVar

from inbox_agent.config import Settings, get_settings
from inbox_agent.obs import get_logger, redact_secret

T = TypeVar("T")
_log = get_logger("llm")


class LLMClient(ABC):
    """A text-in / text-out chat client."""

    model: str = "unknown"

    @abstractmethod
    def complete(self, *, system: str, user: str, max_tokens: int = 512) -> str:
        """Return the assistant's reply to a system + user prompt."""


class RetryExhausted(RuntimeError):
    """All retry attempts were used up."""


def with_retries(
    fn: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
    max_retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn``, retrying retryable errors with exponential backoff.

    ``sleep`` is injectable so tests run instantly. Non-retryable exceptions
    propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            if attempt == max_retries:
                raise RetryExhausted(f"gave up after {max_retries} retries: {exc!r}") from exc
            delay = min(0.5 * 2**attempt, 8.0)
            _log.warning("retrying after %s (sleep %.1fs)", type(exc).__name__, delay)
            sleep(delay)
    raise AssertionError("unreachable")


def _is_retryable(exc: Exception) -> bool:
    """True for transient OpenAI-protocol errors (rate limits, timeouts, 5xx)."""
    import openai

    if isinstance(exc, openai.RateLimitError | openai.APITimeoutError | openai.APIConnectionError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or 500 <= exc.status_code < 600
    return False


class OpenAICompatibleClient(LLMClient):
    """Chat client for any OpenAI-compatible endpoint, with backoff."""

    def __init__(self, *, base_url: str, api_key: str, model: str, max_retries: int = 5) -> None:
        from openai import OpenAI

        # SDK retries are off; we own the backoff loop so it is testable.
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0, max_retries=0)
        self.model = model
        self._max_retries = max_retries
        _log.info("llm ready model=%s url=%s key=%s", model, base_url, redact_secret(api_key))

    def complete(self, *, system: str, user: str, max_tokens: int = 512) -> str:
        def call() -> str:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=0.0,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return (resp.choices[0].message.content or "").strip()

        return with_retries(call, is_retryable=_is_retryable, max_retries=self._max_retries)


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build a client from settings; raises ConfigError if the LLM is unconfigured."""
    settings = settings or get_settings()
    base_url, api_key, model = settings.require_llm()
    return OpenAICompatibleClient(base_url=base_url, api_key=api_key, model=model)
