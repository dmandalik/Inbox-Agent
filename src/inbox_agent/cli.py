"""``inbox-agent`` — four commands that form one pipeline.

    inbox-agent generate-data   # write the synthetic corpus to data/
    inbox-agent ingest          # load a corpus into SQLite (idempotent)
    inbox-agent triage          # classify stored emails
    inbox-agent eval            # score predictions vs. ground truth

Run the whole thing with no key and no network via ``TRIAGE_BACKEND=stub``.

Note: no ``from __future__ import annotations`` here — typer resolves these
annotations at runtime, and stringifying them breaks it.
"""

from pathlib import Path
from typing import Annotated

import typer

from inbox_agent import __version__
from inbox_agent.config import get_settings
from inbox_agent.email_source import build_email_source
from inbox_agent.evals import evaluate, render_confusion, render_markdown, render_text
from inbox_agent.store import open_repository
from inbox_agent.synthetic import (
    DEFAULT_CORPUS_PATH,
    DEFAULT_GOLDEN_PATH,
    generate_corpus,
    write_corpus,
)
from inbox_agent.triage import CATEGORIES, build_classifier

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Inbox AI Agent — synthetic-data triage + eval.",
)

DbOption = Annotated[Path | None, typer.Option(help="SQLite path (default: var/inbox.db).")]


def _fail(message: str) -> typer.Exit:
    """Print an actionable error and exit 1 (no traceback)."""
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"inbox-agent {__version__}")


@app.command("generate-data")
def generate_data(
    corpus: Annotated[Path, typer.Option(help="Corpus JSONL output.")] = DEFAULT_CORPUS_PATH,
    golden: Annotated[Path, typer.Option(help="Golden labels JSONL output.")] = DEFAULT_GOLDEN_PATH,
) -> None:
    """Write the synthetic email corpus and its ground-truth labels."""
    emails = generate_corpus()
    write_corpus(emails, corpus_path=corpus, golden_path=golden)

    typer.echo(f"Generated {len(emails)} synthetic emails.")
    for category in CATEGORIES:
        count = sum(1 for e in emails if e.category == category)
        typer.echo(f"  {category:<14} {count}")
    typer.echo(f"Corpus:  {corpus}\nLabels:  {golden}")


@app.command()
def ingest(
    source: Annotated[
        str, typer.Option(help="'synthetic' (default) or 'gmail' (opt-in).")
    ] = "synthetic",
    corpus: Annotated[Path, typer.Option(help="Synthetic corpus JSONL.")] = DEFAULT_CORPUS_PATH,
    limit: Annotated[int | None, typer.Option(help="Max messages to ingest.")] = None,
    db: DbOption = None,
) -> None:
    """Ingest emails into SQLite. Idempotent — safe to re-run."""
    if source == "synthetic" and not corpus.exists():
        raise _fail(f"No corpus at {corpus}. Run `inbox-agent generate-data` first.")
    try:
        email_source = build_email_source(source, corpus_path=corpus)
        emails = list(email_source.fetch(limit=limit))
    except Exception as exc:
        raise _fail(str(exc)) from exc

    db_path = db or get_settings().db_path
    repo = open_repository(db_path)
    before = repo.count()
    repo.add_many(emails)
    added = repo.count() - before
    repo.close()
    typer.echo(
        f"Ingested {len(emails)} emails from '{email_source.name}' into {db_path} "
        f"({added} new, {len(emails) - added} already present)."
    )


@app.command()
def triage(
    backend: Annotated[
        str | None, typer.Option(help="Override TRIAGE_BACKEND: 'stub' or 'llm'.")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Classify at most N emails.")] = None,
    db: DbOption = None,
) -> None:
    """Classify stored emails into triage categories."""
    settings = get_settings()
    if backend:
        settings = settings.model_copy(update={"triage_backend": backend})
    try:
        classifier = build_classifier(settings)
    except Exception as exc:  # ConfigError when `llm` has no key
        raise _fail(str(exc)) from exc

    repo = open_repository(db or settings.db_path)
    emails = repo.all()
    if not emails:
        repo.close()
        raise _fail("No emails in the DB. Run `inbox-agent ingest` first.")

    emails = emails[:limit] if limit else emails
    typer.echo(f"Triaging {len(emails)} emails with '{classifier.name}' backend…")
    predictions = classifier.classify_many(emails)
    for message_id, category in predictions.items():
        repo.set_prediction(message_id, category, backend=classifier.name)
    repo.close()

    for category in CATEGORIES:
        count = sum(1 for c in predictions.values() if c == category)
        typer.echo(f"  {category:<14} {count}")
    typer.echo(f"Wrote {len(predictions)} predictions.")


@app.command("eval")
def eval_(
    db: DbOption = None,
    markdown: Annotated[
        bool, typer.Option("--markdown", help="Also print a Markdown table.")
    ] = False,
) -> None:
    """Score triage predictions against ground-truth labels."""
    repo = open_repository(db or get_settings().db_path)
    ground_truth, predictions = repo.ground_truth(), repo.predictions()
    backends = repo.prediction_backends()
    repo.close()

    if not predictions:
        raise _fail("No predictions in the DB. Run `inbox-agent triage` first.")

    try:
        result = evaluate(
            ground_truth, predictions, backend=", ".join(sorted(backends)) or "unknown"
        )
    except ValueError as exc:
        raise _fail(str(exc)) from exc

    typer.echo(render_text(result))
    typer.echo("")
    typer.echo(render_confusion(result))
    if markdown:
        typer.echo("")
        typer.echo(render_markdown(result))


if __name__ == "__main__":
    app()
