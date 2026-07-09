"""Structured-ish logging setup.

A single ``get_logger`` entry point so every module logs the same way and
Phase 4 can redirect to a real backend from one place. We emit key=value
records via ``logger.info("msg", extra={...})`` conventions handled by the
formatter below. Redaction is the caller's responsibility (use ``obs.redact``).
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s :: %(message)s"))
    root = logging.getLogger("inbox_agent")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``inbox_agent`` root."""
    _configure_root()
    return logging.getLogger(f"inbox_agent.{name}")
