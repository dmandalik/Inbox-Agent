"""``inbox-agent`` command-line entrypoint.

Milestone 1 wires four commands into one pipeline::

    inbox-agent generate-data   # write a synthetic corpus to data/synthetic/
    inbox-agent ingest          # load a corpus into SQLite (idempotent)
    inbox-agent triage          # classify stored emails (stub or llm backend)
    inbox-agent eval            # score predictions vs. ground-truth labels

This module is a runnable stub in the scaffolding commit; each command is
wired to its implementation in subsequent commits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from inbox_agent import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Inbox AI Agent — synthetic-data triage + eval (Milestone 1).",
)

_PENDING = "This command is scaffolded and will be wired in a later commit."


@app.callback()
def _root() -> None:
    """Inbox AI Agent CLI."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"inbox-agent {__version__}")


@app.command("generate-data")
def generate_data(
    seed: Annotated[int, typer.Option(help="Seed for the deterministic generator.")] = 1337,
    corpus: Annotated[
        Path | None,
        typer.Option(help="Corpus JSONL output path (default: data/synthetic/corpus.jsonl)."),
    ] = None,
    golden: Annotated[
        Path | None,
        typer.Option(help="Golden labels JSONL output path (default: data/golden/labels.jsonl)."),
    ] = None,
) -> None:
    """Generate a synthetic email corpus into data/synthetic/."""
    from inbox_agent.synthetic import (
        DEFAULT_CORPUS_PATH,
        DEFAULT_GOLDEN_PATH,
        generate_corpus,
        write_corpus,
    )
    from inbox_agent.triage import CATEGORIES

    emails = generate_corpus(seed=seed)
    corpus_path, golden_path = write_corpus(
        emails,
        corpus_path=corpus or DEFAULT_CORPUS_PATH,
        golden_path=golden or DEFAULT_GOLDEN_PATH,
    )
    counts = dict.fromkeys(CATEGORIES, 0)
    for e in emails:
        if e.category in counts:
            counts[e.category] += 1
    typer.echo(f"Generated {len(emails)} synthetic emails (seed={seed}).")
    for cat in CATEGORIES:
        typer.echo(f"  {cat:<14} {counts[cat]}")
    typer.echo(f"Corpus:  {corpus_path}")
    typer.echo(f"Labels:  {golden_path}")


@app.command()
def ingest() -> None:
    """Ingest a corpus into SQLite (idempotent)."""
    typer.echo(_PENDING)


@app.command()
def triage() -> None:
    """Classify stored emails into triage categories."""
    typer.echo(_PENDING)


@app.command("eval")
def eval_() -> None:
    """Score triage predictions against ground-truth labels."""
    typer.echo(_PENDING)


if __name__ == "__main__":
    app()
