"""Synthetic, entirely-fake email generation.

The generator is deterministic (seeded) so the committed corpus is stable and
tests/eval numbers are reproducible. It invents all names, uses only
``example.*`` domains, and never scrapes or copies real data.
"""

from inbox_agent.synthetic.generator import (
    DEFAULT_CORPUS_PATH,
    DEFAULT_GOLDEN_PATH,
    generate_corpus,
    write_corpus,
)

__all__ = [
    "DEFAULT_CORPUS_PATH",
    "DEFAULT_GOLDEN_PATH",
    "generate_corpus",
    "write_corpus",
]
