"""Per-message summary cache. LLM mocked — no network."""

from __future__ import annotations

from inbox_agent.llm import LLMClient
from inbox_agent.models import Email
from inbox_agent.store import open_repository
from inbox_agent.summarize import Summarizer, heuristic_summary


class CountingLLM(LLMClient):
    """Returns a scripted summary and counts how often it is called."""

    def __init__(self, reply: str = "Priya needs the Q3 doc by Friday.") -> None:
        self.reply = reply
        self.model = "fake"
        self.calls = 0

    def complete(self, *, system: str, user: str, max_tokens: int = 512) -> str:
        self.calls += 1
        return self.reply


class BoomLLM(LLMClient):
    model = "boom"

    def complete(self, *, system, user, max_tokens=512):
        raise RuntimeError("model down")


def _email(mid: str = "m1", body: str = "The planning doc is due Friday.") -> Email:
    return Email(
        message_id=mid,
        thread_id="t1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="priya@northwind.example.com",
        from_name="Priya",
        subject="Q3 planning",
        body=body,
    )


def test_heuristic_summary_is_keyless_and_truncates():
    long_body = " ".join(f"w{i}" for i in range(100))
    s = heuristic_summary(_email(body=long_body), max_words=10)
    assert s.startswith("Priya: Q3 planning")
    assert s.endswith("…")  # long bodies are cut


def test_summary_is_generated_then_cached():
    repo = open_repository(":memory:")
    fake = CountingLLM()
    summ = Summarizer(repo, fake)
    email = _email()

    first = summ.summary_for(email)
    second = summ.summary_for(email)  # served from cache

    assert first == second == "Priya needs the Q3 doc by Friday."
    assert fake.calls == 1  # generated once, never again
    assert repo.get_summary("m1") == first


def test_cache_survives_a_new_summarizer_instance():
    """Immutability: the cache is in the DB, not the object."""
    repo = open_repository(":memory:")
    fake = CountingLLM()
    Summarizer(repo, fake).summary_for(_email())
    # A fresh summarizer (e.g. a new request) reuses the stored summary.
    Summarizer(repo, fake).summary_for(_email())
    assert fake.calls == 1


def test_no_client_uses_heuristic_and_still_caches():
    repo = open_repository(":memory:")
    summ = Summarizer(repo, client=None)
    out = summ.summary_for(_email())
    assert "Priya" in out
    assert repo.get_summary("m1") == out


def test_generation_error_degrades_to_heuristic():
    repo = open_repository(":memory:")
    out = Summarizer(repo, BoomLLM()).summary_for(_email())
    assert "Priya" in out  # heuristic fallback, not a crash


def test_summaries_for_batches_and_generates_only_misses():
    repo = open_repository(":memory:")
    fake = CountingLLM()
    summ = Summarizer(repo, fake)
    e1, e2 = _email("m1"), _email("m2")
    summ.summary_for(e1)  # warm the cache for m1 (1 call)
    fake.calls = 0

    out = summ.summaries_for([e1, e2])
    assert set(out) == {"m1", "m2"}
    assert fake.calls == 1  # only m2 was generated
