"""Tests for the deterministic synthetic email generator."""

from __future__ import annotations

import json

from inbox_agent.synthetic import generate_corpus, write_corpus
from inbox_agent.synthetic.generator import load_corpus
from inbox_agent.triage import CATEGORIES


def test_generator_is_deterministic():
    a = generate_corpus(seed=1337)
    b = generate_corpus(seed=1337)
    assert [e.to_json() for e in a] == [e.to_json() for e in b]


def test_all_categories_present_and_valid():
    emails = generate_corpus()
    seen = {e.category for e in emails}
    assert seen == set(CATEGORIES), f"expected all categories, got {seen}"
    assert all(e.category in CATEGORIES for e in emails)


def test_message_ids_unique_and_sequential():
    emails = generate_corpus()
    ids = [e.message_id for e in emails]
    assert len(ids) == len(set(ids)), "message_ids must be unique"
    assert ids[0] == "msg-0001"


def test_synthetic_uses_only_fake_domains():
    emails = generate_corpus()
    for e in emails:
        for addr in [e.from_addr, *e.to, *e.cc]:
            domain = addr.split("@")[-1]
            assert ".example." in f".{domain}." or domain.endswith(
                (".example.com", ".example.org", ".example.net", ".example.biz")
            ), f"non-fake domain leaked: {addr}"


def test_work_threads_are_multi_message():
    emails = generate_corpus()
    thread_sizes: dict[str, int] = {}
    for e in emails:
        if e.category == "work":
            thread_sizes[e.thread_id] = thread_sizes.get(e.thread_id, 0) + 1
    assert max(thread_sizes.values()) >= 2, "expected at least one multi-message work thread"


def test_injection_samples_present_and_labeled_spam():
    emails = generate_corpus()
    injections = [
        e
        for e in emails
        if "ignore all previous instructions" in e.body.lower()
        or "system override" in e.body.lower()
    ]
    assert len(injections) >= 2, "expected >=2 prompt-injection samples for Phase 3"
    assert all(e.category == "spam_phishing" for e in injections)


def test_write_and_reload_roundtrip(tmp_path):
    emails = generate_corpus()
    corpus_path = tmp_path / "corpus.jsonl"
    golden_path = tmp_path / "labels.jsonl"
    write_corpus(emails, corpus_path=corpus_path, golden_path=golden_path)

    reloaded = load_corpus(corpus_path)
    assert [e.to_json() for e in reloaded] == [e.to_json() for e in emails]

    golden_lines = golden_path.read_text().strip().splitlines()
    assert len(golden_lines) == len(emails)
    first = json.loads(golden_lines[0])
    assert set(first.keys()) == {"message_id", "category"}
