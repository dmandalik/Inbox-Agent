"""Tests for the EmailSource interface: synthetic default + Gmail guardrails."""

from __future__ import annotations

import pytest

from inbox_agent.email_source import SyntheticEmailSource, build_email_source
from inbox_agent.email_source.gmail import GmailEmailSource, GmailNotConfigured
from inbox_agent.synthetic import generate_corpus


def test_synthetic_source_yields_full_corpus_from_file(tmp_path):
    from inbox_agent.synthetic import write_corpus

    corpus = tmp_path / "corpus.jsonl"
    golden = tmp_path / "labels.jsonl"
    write_corpus(generate_corpus(), corpus_path=corpus, golden_path=golden)

    src = SyntheticEmailSource(corpus_path=corpus)
    emails = list(src.fetch())
    assert len(emails) == len(generate_corpus())
    assert src.name == "synthetic"


def test_synthetic_source_generates_when_no_file(tmp_path):
    # Point at a non-existent file -> falls back to deterministic generation.
    src = SyntheticEmailSource(corpus_path=tmp_path / "missing.jsonl", seed=1337)
    emails = list(src.fetch())
    assert [e.to_json() for e in emails] == [e.to_json() for e in generate_corpus(1337)]


def test_synthetic_source_respects_limit(tmp_path):
    src = SyntheticEmailSource(corpus_path=tmp_path / "missing.jsonl")
    assert len(list(src.fetch(limit=5))) == 5


def test_factory_default_is_synthetic():
    src = build_email_source()
    assert isinstance(src, SyntheticEmailSource)


def test_factory_rejects_unknown_source():
    with pytest.raises(ValueError, match="unknown email source"):
        build_email_source("imap")


def test_gmail_source_rejects_non_readonly_scope():
    # Hard guarantee: Milestone 1 is read-only.
    with pytest.raises(GmailNotConfigured, match="read-only"):
        GmailEmailSource(scope="https://www.googleapis.com/auth/gmail.modify")


def test_gmail_source_is_inert_without_credentials(tmp_path):
    # Never required to run: fetching without creds fails loudly, not silently.
    src = GmailEmailSource(
        credentials_path=tmp_path / "credentials.json",
        token_path=tmp_path / "token.json",
    )
    # Either the optional google libs are missing, or the creds file is absent —
    # both raise our clear GmailNotConfigured, and nothing touches the network.
    with pytest.raises(GmailNotConfigured):
        list(src.fetch())
