"""SQLite storage: schema + an idempotent repository over :class:`Email`.

The repository is the only place that touches SQL, so a different backend could
replace it without changing callers.
"""

from inbox_agent.store.repository import EmailRepository, open_repository

__all__ = ["EmailRepository", "open_repository"]
