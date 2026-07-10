"""The whole pipeline, end to end: generate -> ingest -> triage -> eval.

Runs with the keyless `stub` backend: no API key, no network. This is what CI
executes, so a clean clone is proven to work with no credentials.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from inbox_agent.cli import app
from inbox_agent.triage import CATEGORIES

runner = CliRunner()


@pytest.fixture
def paths(tmp_path):
    return {
        "corpus": tmp_path / "corpus.jsonl",
        "golden": tmp_path / "labels.jsonl",
        "db": tmp_path / "inbox.db",
    }


def run(*args) -> object:
    result = runner.invoke(app, [str(a) for a in args])
    return result


def test_full_flow_with_no_key_and_no_network(paths, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("TRIAGE_BACKEND", "stub")

    r = run("generate-data", "--corpus", paths["corpus"], "--golden", paths["golden"])
    assert r.exit_code == 0, r.output
    assert paths["corpus"].exists() and paths["golden"].exists()

    r = run("ingest", "--corpus", paths["corpus"], "--db", paths["db"])
    assert r.exit_code == 0, r.output
    assert "40 new" in r.output

    # Re-ingesting must not duplicate.
    r = run("ingest", "--corpus", paths["corpus"], "--db", paths["db"])
    assert "0 new" in r.output

    r = run("triage", "--backend", "stub", "--db", paths["db"])
    assert r.exit_code == 0, r.output
    assert "Wrote 40 predictions" in r.output

    r = run("eval", "--db", paths["db"])
    assert r.exit_code == 0, r.output
    assert "backend: stub" in r.output
    assert "macro avg" in r.output
    assert "Confusion matrix" in r.output
    for category in CATEGORIES:
        assert category in r.output


def test_eval_can_print_a_markdown_table(paths, monkeypatch):
    monkeypatch.setenv("TRIAGE_BACKEND", "stub")
    run("generate-data", "--corpus", paths["corpus"], "--golden", paths["golden"])
    run("ingest", "--corpus", paths["corpus"], "--db", paths["db"])
    run("triage", "--backend", "stub", "--db", paths["db"])

    r = run("eval", "--db", paths["db"], "--markdown")
    assert r.exit_code == 0, r.output
    assert "| category | precision | recall | F1 | support |" in r.output
    assert "**macro avg**" in r.output


def test_ingest_without_a_corpus_fails_cleanly(paths):
    r = run("ingest", "--corpus", paths["corpus"], "--db", paths["db"])
    assert r.exit_code == 1
    assert "generate-data" in r.output


def test_triage_without_ingest_fails_cleanly(paths, monkeypatch):
    monkeypatch.setenv("TRIAGE_BACKEND", "stub")
    r = run("triage", "--backend", "stub", "--db", paths["db"])
    assert r.exit_code == 1
    assert "ingest" in r.output


def test_eval_without_triage_fails_cleanly(paths):
    run("generate-data", "--corpus", paths["corpus"], "--golden", paths["golden"])
    run("ingest", "--corpus", paths["corpus"], "--db", paths["db"])

    r = run("eval", "--db", paths["db"])
    assert r.exit_code == 1
    assert "triage" in r.output
