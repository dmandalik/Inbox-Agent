"""Synthetic email source — the default, fully-offline source.

Either loads a previously-written corpus file (so the committed corpus is the
source of truth) or generates one on the fly from a seed. No network, no creds.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from inbox_agent.email_source.base import EmailSource
from inbox_agent.models import Email
from inbox_agent.synthetic.generator import DEFAULT_CORPUS_PATH, generate_corpus, load_corpus


class SyntheticEmailSource(EmailSource):
    """Yield fake emails from a corpus file, or generate them from ``seed``."""

    name = "synthetic"

    def __init__(self, corpus_path: Path | None = DEFAULT_CORPUS_PATH, seed: int = 1337) -> None:
        self.corpus_path = corpus_path
        self.seed = seed

    def fetch(self, limit: int | None = None) -> Iterable[Email]:
        if self.corpus_path is not None and Path(self.corpus_path).exists():
            emails = load_corpus(self.corpus_path)
        else:
            # No file yet — generate deterministically so callers still work.
            emails = generate_corpus(seed=self.seed)
        if limit is not None:
            emails = emails[:limit]
        yield from emails
