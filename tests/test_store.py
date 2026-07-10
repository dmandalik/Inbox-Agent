"""Tests for the SQLite store: round-trip, idempotency, predictions."""

from __future__ import annotations

from inbox_agent.models import Email
from inbox_agent.store import open_repository
from inbox_agent.synthetic import generate_corpus


def _repo():
    # In-memory DB keeps unit tests fast and network/disk-free.
    return open_repository(":memory:")


def _sample() -> Email:
    return Email(
        message_id="msg-0001",
        thread_id="t-1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="alice@example.org",
        from_name="Alice",
        to=["you@example.com"],
        cc=["bob@example.net"],
        subject="Hello",
        body="Body text with commas, and JSON-ish [chars].",
        labels=["INBOX", "IMPORTANT"],
        category="personal",
    )


def test_round_trip_preserves_all_fields():
    repo = _repo()
    e = _sample()
    repo.add(e)
    got = repo.get("msg-0001")
    assert got == e  # frozen dataclass equality covers every field incl. lists


def test_reingestion_is_idempotent():
    repo = _repo()
    emails = generate_corpus()
    repo.add_many(emails)
    n1 = repo.count()
    # Re-ingest the exact same corpus twice — no duplicates.
    repo.add_many(emails)
    repo.add_many(emails)
    assert repo.count() == n1 == len(emails)


def test_reingestion_preserves_predictions():
    repo = _repo()
    e = _sample()
    repo.add(e)
    repo.set_prediction("msg-0001", "work", when="2026-06-16T00:00:00+00:00")
    # Re-ingesting the source email must not wipe the prediction.
    repo.add(e)
    assert repo.get_prediction("msg-0001") == "work"


def test_get_missing_returns_none():
    repo = _repo()
    assert repo.get("nope") is None
    assert repo.get_prediction("nope") is None


def test_set_prediction_unknown_id_raises():
    repo = _repo()
    try:
        repo.set_prediction("ghost", "work")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown message_id")


def test_predictions_and_ground_truth_maps():
    repo = _repo()
    repo.add_many(generate_corpus())
    gt = repo.ground_truth()
    assert len(gt) == repo.count()
    # No predictions yet.
    assert repo.predictions() == {}
    # After predicting a couple, they show up.
    ids = list(gt)[:2]
    for mid in ids:
        repo.set_prediction(mid, "notification")
    preds = repo.predictions()
    assert set(preds) == set(ids)
    assert all(v == "notification" for v in preds.values())


def test_prediction_records_backend():
    repo = _repo()
    repo.add(_sample())
    repo.set_prediction("msg-0001", "work", backend="stub")
    assert repo.prediction_backends() == {"stub"}


def test_prediction_backends_empty_before_triage():
    repo = _repo()
    repo.add(_sample())
    assert repo.prediction_backends() == set()


def test_by_thread_returns_thread_ordered():
    repo = _repo()
    repo.add_many(generate_corpus())
    # Find a multi-message work thread.
    threads: dict[str, int] = {}
    for e in repo.all():
        threads[e.thread_id] = threads.get(e.thread_id, 0) + 1
    multi = [t for t, n in threads.items() if n >= 2][0]
    msgs = repo.by_thread(multi)
    assert len(msgs) >= 2
    assert [m.date for m in msgs] == sorted(m.date for m in msgs)
