"""``inbox-agent`` command-line entrypoint.

Milestone 1 wires four commands into one pipeline::

    inbox-agent generate-data   # write a synthetic corpus to data/synthetic/
    inbox-agent ingest          # load a corpus into SQLite (idempotent)
    inbox-agent triage          # classify stored emails (stub or llm backend)
    inbox-agent eval            # score predictions vs. ground-truth labels

Run end-to-end with no key and no network via ``TRIAGE_BACKEND=stub``.

Implementations are imported lazily inside each command so ``--help`` stays
fast and an unconfigured LLM never blocks the keyless path.
"""

from pathlib import Path
from typing import Annotated

import typer

from inbox_agent import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Inbox AI Agent — synthetic-data triage + eval (Milestone 1).",
)


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
def ingest(
    source: Annotated[
        str, typer.Option(help="Email source: 'synthetic' (default) or 'gmail' (opt-in).")
    ] = "synthetic",
    corpus: Annotated[
        Path | None,
        typer.Option(help="Synthetic corpus JSONL (default: data/synthetic/corpus.jsonl)."),
    ] = None,
    limit: Annotated[
        int | None, typer.Option(help="Max messages to ingest (default: all).")
    ] = None,
    db: Annotated[
        Path | None, typer.Option(help="SQLite path (default: DB_PATH / var/inbox.db).")
    ] = None,
) -> None:
    """Ingest emails from a source into SQLite (idempotent — safe to re-run)."""
    from inbox_agent.config import get_settings
    from inbox_agent.email_source import build_email_source
    from inbox_agent.store import open_repository
    from inbox_agent.synthetic import DEFAULT_CORPUS_PATH

    if source == "synthetic":
        corpus_path = corpus or DEFAULT_CORPUS_PATH
        if not corpus_path.exists():
            typer.secho(
                f"No corpus at {corpus_path}. Run `inbox-agent generate-data` first.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        email_source = build_email_source("synthetic", corpus_path=corpus_path)
    else:
        try:
            email_source = build_email_source(source, settings=get_settings())
        except Exception as exc:  # surface a clean message, not a traceback
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc

    db_path = db or get_settings().db_path
    emails = list(email_source.fetch(limit=limit))
    repo = open_repository(db_path)
    before = repo.count()
    repo.add_many(emails)
    after = repo.count()
    repo.close()
    typer.echo(
        f"Ingested {len(emails)} emails from '{email_source.name}' into {db_path} "
        f"({after - before} new, {len(emails) - (after - before)} already present)."
    )


@app.command()
def triage(
    backend: Annotated[
        str | None,
        typer.Option(help="Override TRIAGE_BACKEND: 'stub' (keyless) or 'llm'."),
    ] = None,
    db: Annotated[
        Path | None, typer.Option(help="SQLite path (default: DB_PATH / var/inbox.db).")
    ] = None,
    limit: Annotated[
        int | None, typer.Option(help="Classify at most N emails (default: all).")
    ] = None,
) -> None:
    """Classify stored emails into triage categories."""
    from inbox_agent.config import get_settings
    from inbox_agent.store import open_repository
    from inbox_agent.triage import build_classifier

    settings = get_settings()
    if backend:
        settings = settings.model_copy(update={"triage_backend": backend})

    try:
        classifier = build_classifier(settings)
    except Exception as exc:  # ConfigError etc. — clean message, no traceback
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    repo = open_repository(db or settings.db_path)
    emails = repo.all()
    if not emails:
        typer.secho(
            "No emails in the DB. Run `inbox-agent ingest` first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if limit is not None:
        emails = emails[:limit]

    typer.echo(f"Triaging {len(emails)} emails with '{classifier.name}' backend…")
    predictions = classifier.classify_many(emails)
    for mid, category in predictions.items():
        repo.set_prediction(mid, category, backend=classifier.name)
    repo.close()

    counts: dict[str, int] = {}
    for category in predictions.values():
        counts[category] = counts.get(category, 0) + 1
    for category in sorted(counts):
        typer.echo(f"  {category:<14} {counts[category]}")
    typer.echo(f"Wrote {len(predictions)} predictions.")


@app.command("eval")
def eval_(
    db: Annotated[
        Path | None, typer.Option(help="SQLite path (default: DB_PATH / var/inbox.db).")
    ] = None,
    markdown: Annotated[
        bool, typer.Option("--markdown", help="Also print a Markdown table (for the README).")
    ] = False,
) -> None:
    """Score triage predictions against ground-truth labels."""
    from inbox_agent.config import get_settings
    from inbox_agent.evals import evaluate, render_confusion, render_markdown, render_text
    from inbox_agent.store import open_repository

    settings = get_settings()
    repo = open_repository(db or settings.db_path)
    ground_truth = repo.ground_truth()
    predictions = repo.predictions()
    backends = repo.prediction_backends()
    repo.close()

    if not predictions:
        typer.secho(
            "No predictions in the DB. Run `inbox-agent triage` first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    backend_label = ", ".join(sorted(backends)) if backends else "unknown"
    try:
        result = evaluate(ground_truth, predictions, backend=backend_label)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(render_text(result))
    typer.echo("")
    typer.echo(render_confusion(result))
    if markdown:
        typer.echo("")
        typer.echo(render_markdown(result))


if __name__ == "__main__":
    app()
