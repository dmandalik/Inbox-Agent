"""A tiny, testable retry-with-backoff helper.

Kept independent of any provider SDK so it can be unit-tested with a plain
exception and an injected ``sleep``. Free LLM tiers are tightly rate-limited, so
429/5xx/timeout responses are expected and must be retried, not crashed on.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from inbox_agent.obs import get_logger

T = TypeVar("T")
_log = get_logger("llm.retry")


class RetryExhausted(RuntimeError):
    """Raised when all retry attempts are used up."""


def with_retries(
    fn: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
    max_retries: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Call ``fn`` with exponential backoff on retryable exceptions.

    ``sleep`` is injectable (default ``time.sleep``) so tests run instantly.
    Non-retryable exceptions propagate immediately. Delays grow as
    ``base_delay * 2**attempt`` capped at ``max_delay``.
    """
    if sleep is None:
        import time

        sleep = time.sleep

    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised unless retryable
            if not is_retryable(exc):
                raise
            if attempt >= max_retries:
                raise RetryExhausted(
                    f"gave up after {max_retries} retries: {type(exc).__name__}: {exc}"
                ) from exc
            delay = min(base_delay * (2**attempt), max_delay)
            _log.warning(
                "retryable error (attempt %d/%d): %s; sleeping %.2fs",
                attempt + 1,
                max_retries,
                type(exc).__name__,
                delay,
            )
            sleep(delay)
            attempt += 1
