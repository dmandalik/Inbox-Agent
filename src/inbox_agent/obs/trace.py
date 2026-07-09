"""Tracing seam.

``traced`` currently just logs entry/exit + duration. It exists so that
Phase 4 can wrap spans (Langfuse / OpenTelemetry) by editing this one file,
with no changes at call sites.

TODO(phase-4): emit real spans (cost, latency, token counts) here.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from inbox_agent.obs.logging import get_logger

P = ParamSpec("P")
R = TypeVar("R")

_log = get_logger("trace")


def traced(name: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that logs a span around the wrapped callable.

    Usage::

        @traced()
        def classify(...): ...

        @traced("llm.chat")
        def _chat(...): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        span = name or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            _log.debug("span.start name=%s", span)
            try:
                return func(*args, **kwargs)
            finally:
                dur_ms = (time.perf_counter() - start) * 1000
                _log.debug("span.end name=%s duration_ms=%.1f", span, dur_ms)

        return wrapper

    return decorator
