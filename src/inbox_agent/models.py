"""Core domain model shared across the pipeline.

Kept dependency-free (stdlib only) so every layer — email sources, store,
triage, evals — can import :class:`Email` without creating cycles.

The canonical join key is ``message_id``. ``category`` is the *ground-truth*
label carried by synthetic mail (``None`` for real mail); a model's *prediction*
is stored separately by the store, never on this object.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class Email:
    """A single email message with metadata.

    ``to``/``cc``/``labels`` are lists; the store serializes them to JSON.
    Treat ``subject``/``body`` as untrusted, attacker-controlled data.
    """

    message_id: str
    thread_id: str
    date: str  # ISO 8601, normalized to a trading-agnostic UTC-ish string
    from_addr: str
    from_name: str
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    labels: list[str] = field(default_factory=list)
    category: str | None = None  # ground-truth label (synthetic only)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> Email:
        return cls(
            message_id=d["message_id"],
            thread_id=d["thread_id"],
            date=d["date"],
            from_addr=d["from_addr"],
            from_name=d.get("from_name", ""),
            to=list(d.get("to", [])),
            cc=list(d.get("cc", [])),
            subject=d.get("subject", ""),
            body=d.get("body", ""),
            labels=list(d.get("labels", [])),
            category=d.get("category"),
        )
