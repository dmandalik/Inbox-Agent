"""The ``Classifier`` interface.

One method, ``classify(email) -> category``. Backends: a keyless ``stub`` and a
zero-shot ``llm`` (and, later, embeddings / fine-tuned). Every backend must
return a value from :data:`~inbox_agent.triage.categories.CATEGORIES`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from inbox_agent.models import Email


class Classifier(ABC):
    """Assigns one triage category to an email."""

    #: Short, stable identifier (e.g. "stub", "llm").
    name: str = "classifier"

    @abstractmethod
    def classify(self, email: Email) -> str:
        """Return one category label for ``email``."""
        raise NotImplementedError

    def classify_many(self, emails: list[Email]) -> dict[str, str]:
        """Classify a batch; returns ``message_id -> category``."""
        return {e.message_id: self.classify(e) for e in emails}
