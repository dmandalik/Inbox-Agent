"""The ``EmailSource`` interface.

Any source of emails — synthetic, Gmail, an mbox importer later — implements
``fetch`` and yields :class:`~inbox_agent.models.Email` objects. Keeping this
narrow means ingestion code never cares where mail came from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from inbox_agent.models import Email


class EmailSource(ABC):
    """Read-only source of emails."""

    #: Short, stable identifier used in logs/CLI (e.g. "synthetic", "gmail").
    name: str = "email-source"

    @abstractmethod
    def fetch(self, limit: int | None = None) -> Iterable[Email]:
        """Yield emails, at most ``limit`` if given.

        Implementations must treat message content as untrusted data and must
        not perform any state-changing operation on the underlying account
        (read-only guarantee for Milestone 1).
        """
        raise NotImplementedError
