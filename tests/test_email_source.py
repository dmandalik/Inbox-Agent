"""Synthetic is the default; Gmail is opt-in, read-only, and inert."""

from __future__ import annotations

import pytest

from inbox_agent.email_source import (
    GmailEmailSource,
    GmailNotConfigured,
    SyntheticEmailSource,
    build_email_source,
)
from inbox_agent.synthetic import generate_corpus, write_corpus


def test_synthetic_source_reads_a_corpus_file(tmp_path):
    corpus, golden = tmp_path / "corpus.jsonl", tmp_path / "labels.jsonl"
    write_corpus(generate_corpus(), corpus_path=corpus, golden_path=golden)
    assert list(SyntheticEmailSource(corpus).fetch()) == generate_corpus()


def test_synthetic_source_generates_when_the_file_is_missing(tmp_path):
    source = SyntheticEmailSource(tmp_path / "missing.jsonl")
    assert list(source.fetch()) == generate_corpus()


def test_synthetic_source_respects_limit(tmp_path):
    assert len(list(SyntheticEmailSource(tmp_path / "missing.jsonl").fetch(limit=5))) == 5


def test_factory_defaults_to_synthetic():
    assert isinstance(build_email_source(), SyntheticEmailSource)


def test_factory_rejects_unknown_source():
    with pytest.raises(ValueError, match="unknown email source"):
        build_email_source("imap")


def test_gmail_refuses_any_non_readonly_scope():
    with pytest.raises(GmailNotConfigured, match="read-only"):
        GmailEmailSource(scope="https://www.googleapis.com/auth/gmail.modify")


def test_gmail_is_inert_without_credentials(tmp_path):
    """Fetching without deps or creds fails loudly, and touches no network."""
    source = GmailEmailSource(
        credentials_path=tmp_path / "credentials.json",
        token_path=tmp_path / "token.json",
    )
    with pytest.raises(GmailNotConfigured):
        list(source.fetch())
