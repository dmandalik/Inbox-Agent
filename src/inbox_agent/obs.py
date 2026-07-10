"""Observability: logging, secret redaction, and a tracing seam.

Deliberately tiny. Phase 4 swaps ``traced`` for real spans (Langfuse /
OpenTelemetry) by editing this one file, with no changes at call sites.

Redaction policy: we never *log* an email body or address at all, so there is
no body-redaction helper to misuse. The only thing that needs masking is a
credential, hence :func:`redact_secret`.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from collections.abc import Callable

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``inbox_agent`` root."""
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-7s %(name)s :: %(message)s"))
        root = logging.getLogger("inbox_agent")
        root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
        root.handlers.clear()
        root.addHandler(handler)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(f"inbox_agent.{name}")


def redact_secret(value: str | None) -> str:
    """Reduce a credential to a non-reversible marker showing only its length."""
    return f"<secret:{len(value)}c>" if value else "<unset>"


def traced(name: str) -> Callable:
    """Log a span around the wrapped callable.

    TODO(phase-4): emit real spans here (cost, latency, token counts).
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                get_logger("trace").debug("span name=%s duration_ms=%.1f", name, duration_ms)

        return wrapper

    return decorator
