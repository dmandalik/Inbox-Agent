"""The synthetic corpus is fake, fixed, and covers every category."""

from __future__ import annotations

import json

from inbox_agent.synthetic import generate_corpus, load_corpus, write_corpus
from inbox_agent.triage import CATEGORIES

FAKE_DOMAINS = ("example.com", "example.org", "example.net", "example.biz")


def test_corpus_is_fixed():
    assert generate_corpus() == generate_corpus()


def test_every_category_is_present():
    assert {e.category for e in generate_corpus()} == set(CATEGORIES)


def test_message_ids_are_unique():
    ids = [e.message_id for e in generate_corpus()]
    assert len(ids) == len(set(ids))
    assert ids[0] == "msg-0001"


def test_only_fake_domains_are_used():
    """Either a bare example.* domain, or a subdomain of one."""
    for email in generate_corpus():
        for address in [email.from_addr, *email.to, *email.cc]:
            domain = address.split("@")[-1]
            is_fake = domain in FAKE_DOMAINS or domain.endswith(
                tuple(f".{d}" for d in FAKE_DOMAINS)
            )
            assert is_fake, f"non-fake domain leaked: {address}"


def test_dates_increase_so_replies_follow_their_parent():
    dates = [e.date for e in generate_corpus()]
    assert dates == sorted(dates)


def test_work_threads_have_multiple_messages():
    threads: dict[str, int] = {}
    for email in generate_corpus():
        if email.category == "work":
            threads[email.thread_id] = threads.get(email.thread_id, 0) + 1
    assert max(threads.values()) >= 2


def test_injection_samples_exist_and_are_labeled_spam():
    injections = [
        e
        for e in generate_corpus()
        if "ignore all previous instructions" in e.body.lower()
        or "system override" in e.body.lower()
    ]
    assert len(injections) >= 2  # kept for the Phase 3 security work
    assert all(e.category == "spam_phishing" for e in injections)


def test_write_then_load_round_trips(tmp_path):
    emails = generate_corpus()
    corpus, golden = tmp_path / "corpus.jsonl", tmp_path / "labels.jsonl"
    write_corpus(emails, corpus_path=corpus, golden_path=golden)

    assert load_corpus(corpus) == emails

    labels = [json.loads(line) for line in golden.read_text().splitlines()]
    assert len(labels) == len(emails)
    assert set(labels[0]) == {"message_id", "category"}
