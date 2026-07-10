"""Where emails come from, behind one interface.

``SyntheticEmailSource`` is the default and needs nothing. ``GmailEmailSource``
is an opt-in, read-only stub: it can never run by accident, and it refuses any
scope other than ``gmail.readonly``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from inbox_agent.models import Email
from inbox_agent.synthetic import DEFAULT_CORPUS_PATH, generate_corpus, load_corpus

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class EmailSource(ABC):
    """A read-only source of emails."""

    name: str = "email-source"

    @abstractmethod
    def fetch(self, limit: int | None = None) -> Iterator[Email]:
        """Yield emails, at most ``limit`` if given. Must never mutate the source."""


class SyntheticEmailSource(EmailSource):
    """Fake emails from a corpus file, or generated if the file is absent."""

    name = "synthetic"

    def __init__(self, corpus_path: Path | None = DEFAULT_CORPUS_PATH) -> None:
        self.corpus_path = corpus_path

    def fetch(self, limit: int | None = None) -> Iterator[Email]:
        if self.corpus_path and Path(self.corpus_path).exists():
            emails = load_corpus(self.corpus_path)
        else:
            emails = generate_corpus()
        yield from emails[:limit] if limit else emails


class GmailNotConfigured(RuntimeError):
    """The Gmail path was used without its optional deps or credentials."""


class GmailEmailSource(EmailSource):
    """Opt-in, read-only Gmail source. Not implemented yet — see TODO below.

    Setup, when you want it (you provide the credentials; never paste them
    anywhere but the git-ignored ``var/``):

    1. Create a Google Cloud project and enable the **Gmail API**.
    2. Configure an OAuth consent screen and add yourself as a test user.
    3. Create an OAuth client ID of type *Desktop app* and download the JSON.
    4. Save it to ``var/credentials.json`` (or set ``GMAIL_CREDENTIALS_PATH``).
       The cached token goes to ``var/token.json``. Both are git-ignored.
    5. Install the optional dependencies: ``uv sync --extra gmail``

    Privacy: once a real inbox is connected, switch the LLM to a local model
    (Ollama) or a documented no-training provider. Real email must never be
    sent to a free tier that trains on prompts.

    TODO(phase-0): implement fetch() via the Gmail API (messages.list +
    messages.get, format="full"), mapping payload headers to Email and leaving
    ``category=None`` — real mail has no ground-truth label.
    TODO(phase-3): trust-label fetched content before it reaches any tool.
    """

    name = "gmail"

    def __init__(
        self,
        credentials_path: Path = Path("var/credentials.json"),
        token_path: Path = Path("var/token.json"),
        scope: str = READONLY_SCOPE,
    ) -> None:
        # Hard guarantee: this class is read-only.
        if scope != READONLY_SCOPE:
            raise GmailNotConfigured(
                f"This project is read-only; refusing scope {scope!r}. "
                f"Only {READONLY_SCOPE!r} is permitted."
            )
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.scope = scope

    def fetch(self, limit: int | None = None) -> Iterator[Email]:
        try:
            import googleapiclient.discovery  # noqa: F401
        except ImportError as exc:
            raise GmailNotConfigured(
                "The Gmail source needs optional dependencies:\n"
                "    uv sync --extra gmail\n"
                "The synthetic source (the default) needs none of this."
            ) from exc
        if not self.credentials_path.exists():
            raise GmailNotConfigured(
                f"No OAuth client credentials at {self.credentials_path}. "
                "See this class's docstring for the setup steps."
            )
        raise GmailNotConfigured(
            "The Gmail source is a documented stub and is not implemented yet "
            "(see TODO(phase-0)). Milestone 1 runs entirely on synthetic data."
        )


def build_email_source(kind: str = "synthetic", *, corpus_path: Path | None = None) -> EmailSource:
    """Return the email source named by ``kind`` ("synthetic" | "gmail")."""
    if kind == "synthetic":
        return SyntheticEmailSource(corpus_path or DEFAULT_CORPUS_PATH)
    if kind == "gmail":
        from inbox_agent.config import get_settings

        settings = get_settings()
        return GmailEmailSource(
            credentials_path=settings.gmail_credentials_path,
            token_path=settings.gmail_token_path,
            scope=settings.gmail_scope,
        )
    raise ValueError(f"unknown email source: {kind!r} (expected 'synthetic' or 'gmail')")
