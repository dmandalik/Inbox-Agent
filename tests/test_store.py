"""The store round-trips emails and re-ingestion never duplicates or clobbers."""

from __future__ import annotations

import pytest

from inbox_agent.models import Email
from inbox_agent.store import open_repository
from inbox_agent.synthetic import generate_corpus


def repo():
    # In-memory: unit tests touch neither disk nor network.
    return open_repository(":memory:")


def sample() -> Email:
    return Email(
        message_id="msg-0001",
        thread_id="t-1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="alice@example.org",
        from_name="Alice",
        to=["you@example.com"],
        cc=["bob@example.net"],
        subject="Hello",
        body="Body with commas, and JSON-ish [chars].",
        labels=["INBOX", "IMPORTANT"],
        category="personal",
    )


def test_round_trip_preserves_every_field():
    r = repo()
    r.add(sample())
    assert r.get("msg-0001") == sample()  # frozen dataclass eq covers all fields


def test_reingestion_never_duplicates():
    r = repo()
    emails = generate_corpus()
    r.add_many(emails)
    r.add_many(emails)
    r.add_many(emails)
    assert r.count() == len(emails)


def test_reingestion_preserves_predictions():
    r = repo()
    r.add(sample())
    r.set_prediction("msg-0001", "work", backend="stub")
    r.add(sample())  # re-ingest the same source email
    assert r.get_prediction("msg-0001") == "work"


def test_missing_ids_return_none():
    r = repo()
    assert r.get("nope") is None
    assert r.get_prediction("nope") is None


def test_predicting_unknown_id_raises():
    with pytest.raises(KeyError):
        repo().set_prediction("ghost", "work", backend="stub")


def test_prediction_and_ground_truth_maps():
    r = repo()
    r.add_many(generate_corpus())
    assert len(r.ground_truth()) == r.count()
    assert r.predictions() == {}
    assert r.prediction_backends() == set()

    ids = list(r.ground_truth())[:2]
    for message_id in ids:
        r.set_prediction(message_id, "notification", backend="stub")
    assert set(r.predictions()) == set(ids)
    assert r.prediction_backends() == {"stub"}


def test_by_thread_returns_messages_oldest_first():
    r = repo()
    r.add_many(generate_corpus())
    messages = r.by_thread("wk-1")  # a three-message work thread
    assert len(messages) == 3
    assert [m.date for m in messages] == sorted(m.date for m in messages)
