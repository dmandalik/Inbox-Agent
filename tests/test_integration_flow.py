"""End-to-end pipeline test: generate -> ingest -> triage -> eval.

Runs entirely with the keyless ``stub`` backend: no API key, no network. This
is what CI executes, so the full flow is proven to work from a clean checkout.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from inbox_agent.cli import app

runner = CliRunner()


@pytest.mark.integration
def test_full_flow_keyless(tmp_path, monkeypatch):
    # Guarantee no credentials leak in from a developer's environment.
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("TRIAGE_BACKEND", "stub")

    corpus = tmp_path / "corpus.jsonl"
    golden = tmp_path / "labels.jsonl"
    db = tmp_path / "inbox.db"

    # 1. generate-data
    r = runner.invoke(app, ["generate-data", "--corpus", str(corpus), "--golden", str(golden)])
    assert r.exit_code == 0, r.output
    assert corpus.exists() and golden.exists()
    assert "Generated" in r.output

    # 2. ingest (and prove idempotency by running it twice)
    r = runner.invoke(app, ["ingest", "--corpus", str(corpus), "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "40 new" in r.output

    r = runner.invoke(app, ["ingest", "--corpus", str(corpus), "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "0 new" in r.output  # no duplicates on re-ingest

    # 3. triage with the keyless stub backend
    r = runner.invoke(app, ["triage", "--backend", "stub", "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "Wrote 40 predictions" in r.output

    # 4. eval
    r = runner.invoke(app, ["eval", "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "backend: stub" in r.output
    assert "macro avg" in r.output
    assert "Confusion matrix" in r.output
    # Every category appears as a row in the per-class table.
    for category in (
        "newsletter",
        "work",
        "receipt_order",
        "personal",
        "spam_phishing",
        "notification",
    ):
        assert category in r.output


@pytest.mark.integration
def test_ingest_without_corpus_fails_cleanly(tmp_path):
    r = runner.invoke(
        app, ["ingest", "--corpus", str(tmp_path / "nope.jsonl"), "--db", str(tmp_path / "x.db")]
    )
    assert r.exit_code == 1
    assert "generate-data" in r.output


@pytest.mark.integration
def test_triage_without_ingest_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIAGE_BACKEND", "stub")
    r = runner.invoke(app, ["triage", "--backend", "stub", "--db", str(tmp_path / "empty.db")])
    assert r.exit_code == 1
    assert "ingest" in r.output


@pytest.mark.integration
def test_eval_without_triage_fails_cleanly(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    golden = tmp_path / "labels.jsonl"
    db = tmp_path / "inbox.db"
    runner.invoke(app, ["generate-data", "--corpus", str(corpus), "--golden", str(golden)])
    runner.invoke(app, ["ingest", "--corpus", str(corpus), "--db", str(db)])

    r = runner.invoke(app, ["eval", "--db", str(db)])
    assert r.exit_code == 1
    assert "triage" in r.output


@pytest.mark.integration
def test_eval_markdown_table(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIAGE_BACKEND", "stub")
    corpus = tmp_path / "corpus.jsonl"
    golden = tmp_path / "labels.jsonl"
    db = tmp_path / "inbox.db"
    runner.invoke(app, ["generate-data", "--corpus", str(corpus), "--golden", str(golden)])
    runner.invoke(app, ["ingest", "--corpus", str(corpus), "--db", str(db)])
    runner.invoke(app, ["triage", "--backend", "stub", "--db", str(db)])

    r = runner.invoke(app, ["eval", "--db", str(db), "--markdown"])
    assert r.exit_code == 0, r.output
    assert "| category | precision | recall | F1 | support |" in r.output
    assert "**macro avg**" in r.output
