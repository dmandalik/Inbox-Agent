"""Redaction helpers.

Guardrail: never log or surface full email bodies, addresses at scale,
credentials, or tokens. These helpers are the single place that policy lives,
so logging and exception messages can call them by default.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def redact_address(address: str) -> str:
    """Mask the local-part of an email address: ``alice@example.com`` -> ``a***@example.com``.

    Enough to keep logs debuggable (domain + first char) without exposing the
    full identity.
    """
    if not address:
        return address
    return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", address)


def redact_body(body: str, keep: int = 60) -> str:
    """Truncate a body to ``keep`` chars and mark it redacted.

    Bodies are attacker-controlled and may contain PII; we never emit them in
    full. Whitespace is collapsed so multi-line content stays on one log line.
    """
    if body is None:
        return ""
    collapsed = " ".join(body.split())
    if len(collapsed) <= keep:
        return f"{collapsed} [redacted:{len(collapsed)}c]"
    return f"{collapsed[:keep]}… [redacted:{len(collapsed)}c]"


def redact_secret(value: str | None) -> str:
    """Reduce any secret-like value to a non-reversible marker.

    Shows only the length so you can tell "set" from "empty" without leaking
    the value. Used for API keys and tokens in logs/errors.
    """
    if not value:
        return "<unset>"
    return f"<secret:{len(value)}c>"
