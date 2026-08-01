"""The one domain object: an email.

Stdlib only, so every layer can import it without cycles. The join key is
``message_id``. ``category`` is the *ground-truth* label (synthetic mail only);
a model's *prediction* is stored by the repository, never on this object.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class Email:
    """A single email message. Treat ``subject``/``body`` as untrusted data."""

    message_id: str
    thread_id: str
    date: str  # ISO 8601
    from_addr: str
    from_name: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""  # plain text — used for retrieval, triage, summaries
    body_html: str = ""  # original HTML, if any — rendered (sanitized) in the UI
    labels: list[str] = field(default_factory=list)
    category: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Email:
        return cls(**d)
