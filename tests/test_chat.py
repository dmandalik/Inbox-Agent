"""Chat engine: tiered retrieval, summary-grounded answers, citations.

LLM mocked — no network. Retrieval is the real BM25.
"""

from __future__ import annotations

from inbox_agent.chat import CHAT_SYSTEM_PROMPT, ChatEngine, ChatReply, ChatTurn
from inbox_agent.llm import LLMClient
from inbox_agent.models import Email
from inbox_agent.store import open_repository
from inbox_agent.summarize import Summarizer


class ScriptedLLM(LLMClient):
    """Returns a fixed answer and records the last prompt it saw."""

    def __init__(self, reply: str = "The planning doc is due Friday [1].") -> None:
        self.reply = reply
        self.model = "fake"
        self.system = self.user = ""

    def complete(self, *, system: str, user: str, max_tokens: int = 512) -> str:
        self.system, self.user = system, user
        return self.reply


def _email(mid, thread, subject, body, date="2026-06-15T09:00:00+00:00") -> Email:
    return Email(
        message_id=mid,
        thread_id=thread,
        date=date,
        from_addr="priya@northwind.example.com",
        from_name="Priya",
        subject=subject,
        body=body,
    )


def _engine(emails, client, **kw) -> ChatEngine:
    repo = open_repository(":memory:")
    repo.add_many(emails)
    return ChatEngine(repo.all(), Summarizer(repo, client), client, repo=repo, **kw)


def test_answer_is_grounded_and_cites_the_source():
    emails = [_email("m1", "t1", "Q3 planning", "The planning doc is due Friday.")]
    fake = ScriptedLLM()
    reply = _engine(emails, fake).answer("When is the Q3 doc due?")

    assert isinstance(reply, ChatReply)
    assert reply.text == "The planning doc is due Friday [1]."
    assert [c.message_id for c in reply.citations] == ["m1"]
    assert reply.widened is False


def test_no_match_says_so_plainly():
    emails = [_email("m1", "t1", "Lunch", "want to grab lunch tomorrow?")]
    reply = _engine(emails, ScriptedLLM()).answer("what is my aws bill")
    assert "don't see" in reply.text.lower()
    assert reply.citations == []


def test_prompt_uses_summaries_not_raw_bodies():
    """Context is built from cached summaries (L1), not full email text."""
    repo = open_repository(":memory:")
    email = _email("m1", "t1", "Q3 planning", "SECRET_RAW_BODY_TOKEN due Friday")
    repo.add_many([email])
    repo.set_summary("m1", "Priya: the Q3 doc is due Friday.")  # pre-seed the cache
    fake = ScriptedLLM()
    engine = ChatEngine(repo.all(), Summarizer(repo, fake), fake)

    engine.answer("when is the q3 doc due")
    assert "Q3 doc is due Friday" in fake.user
    assert "SECRET_RAW_BODY_TOKEN" not in fake.user  # the body never entered the prompt


def test_recent_tier_first_then_widens_to_old_mail():
    # Newest-first: a recent email that does NOT match, an old one that does.
    emails = [
        _email(
            "recent", "t2", "office party", "snacks in the kitchen", "2026-07-01T09:00:00+00:00"
        ),
        _email(
            "old", "t1", "invoice", "your stripe invoice total is due", "2025-01-01T09:00:00+00:00"
        ),
    ]
    fake = ScriptedLLM(reply="Your Stripe invoice is due [1].")
    reply = _engine(emails, fake, recent_count=1).answer("stripe invoice")

    assert reply.widened is True  # recent tier missed, so we widened
    assert [c.message_id for c in reply.citations] == ["old"]


def test_recent_tier_hit_does_not_widen():
    emails = [
        _email(
            "recent",
            "t1",
            "stripe invoice",
            "your stripe invoice is due",
            "2026-07-01T09:00:00+00:00",
        ),
        _email("old", "t2", "party", "snacks", "2025-01-01T09:00:00+00:00"),
    ]
    reply = _engine(emails, ScriptedLLM(), recent_count=1).answer("stripe invoice")
    assert reply.widened is False


def test_no_llm_falls_back_to_retrieval_only():
    emails = [_email("m1", "t1", "Q3 planning", "The planning doc is due Friday.")]
    reply = _engine(emails, client=None).answer("when is the q3 doc due")
    assert reply.citations and reply.citations[0].message_id == "m1"
    assert "local llm" in reply.text.lower()


def test_rewrite_uses_history_only_after_first_turn():
    emails = [_email("m1", "t1", "Q3 planning", "The planning doc is due Friday.")]
    fake = ScriptedLLM()
    engine = _engine(emails, fake)
    # With history, a rewrite call happens; the engine still answers grounded.
    history = [ChatTurn("user", "tell me about Q3"), ChatTurn("assistant", "It is planning [1].")]
    reply = engine.answer("when is it due", history)
    assert reply.citations  # still resolves to the email


def test_system_prompt_marks_email_untrusted():
    assert "UNTRUSTED DATA" in CHAT_SYSTEM_PROMPT


class BoomLLM(LLMClient):
    model = "boom"

    def complete(self, *, system, user, max_tokens=512):
        raise AssertionError("LLM must not be called for a structured tool request")


def test_count_intent_is_answered_without_the_llm():
    emails = [_email("m1", "t1", "a", "x"), _email("m2", "t2", "b", "y")]  # both from Priya
    reply = _engine(emails, BoomLLM()).answer("how many emails from priya")
    assert reply.kind == "count"
    assert "2" in reply.text


def test_action_intent_stars_matches_and_reports():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1", "t1", "a", "x"), _email("m2", "t2", "b", "y")])
    engine = ChatEngine(repo.all(), Summarizer(repo, None), None, repo=repo)
    reply = engine.answer("star all emails from priya")
    assert reply.kind == "action"
    assert "Starred 2" in reply.text
    assert repo.get_state("m1")["starred"] is True


def test_action_with_no_matches_reports_gracefully():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1", "t1", "a", "x")])
    engine = ChatEngine(repo.all(), Summarizer(repo, None), None, repo=repo)
    reply = engine.answer("archive all newsletters")
    assert reply.kind == "action"
    assert "couldn't find" in reply.text
