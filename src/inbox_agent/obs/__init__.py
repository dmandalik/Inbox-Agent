"""Observability seam: structured logging, redaction, and a tracing decorator.

Kept deliberately thin so Phase 4 can swap in Langfuse / OpenTelemetry without
touching call sites.
"""

from inbox_agent.obs.logging import get_logger
from inbox_agent.obs.redact import redact_address, redact_body, redact_secret
from inbox_agent.obs.trace import traced

__all__ = [
    "get_logger",
    "redact_address",
    "redact_body",
    "redact_secret",
    "traced",
]
