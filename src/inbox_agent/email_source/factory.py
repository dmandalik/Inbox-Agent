"""Select an :class:`EmailSource` by name.

``synthetic`` is the default and needs nothing. ``gmail`` is opt-in and pulls
config (paths/scope) from settings; it stays inert until you provide creds.
"""

from __future__ import annotations

from pathlib import Path

from inbox_agent.email_source.base import EmailSource
from inbox_agent.email_source.synthetic import SyntheticEmailSource


def build_email_source(
    kind: str = "synthetic",
    *,
    corpus_path: Path | None = None,
    settings=None,
) -> EmailSource:
    """Return an email source for ``kind`` ("synthetic" | "gmail")."""
    kind = kind.lower()
    if kind == "synthetic":
        if corpus_path is not None:
            return SyntheticEmailSource(corpus_path=corpus_path)
        return SyntheticEmailSource()
    if kind == "gmail":
        # Imported lazily so the google deps are only needed on this path.
        from inbox_agent.email_source.gmail import GmailEmailSource

        if settings is None:
            from inbox_agent.config import get_settings

            settings = get_settings()
        return GmailEmailSource(
            credentials_path=settings.gmail_credentials_path,
            token_path=settings.gmail_token_path,
            scope=settings.gmail_scope,
        )
    raise ValueError(f"unknown email source: {kind!r} (expected 'synthetic' or 'gmail')")
