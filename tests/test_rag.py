"""Answer generation over retrieved emails. LLM mocked — no network."""

from __future__ import annotations

import pytest

from inbox_agent.llm import LLMClient
from inbox_agent.models import Email
from inbox_agent.rag import QA_SYSTEM_PROMPT, Answer, answer_question, is_local_llm
from inbox_agent.retrieval import Hit


class FakeLLM(LLMClient):
    """Records the prompt it was given and returns a scripted answer."""

    def __init__(self, reply: str = "The doc is due Friday [1].") -> None:
        self.reply = reply
        self.model = "fake"
        self.system = self.user = ""

    def complete(self, *, system: str, user: str, max_tokens: int = 512) -> str:
        self.system, self.user = system, user
        return self.reply


def _hit(message_id: str, subject: str, body: str) -> Hit:
    email = Email(
        message_id=message_id,
        thread_id="t1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="priya@northwind.example.com",
        from_name="Priya",
        subject=subject,
        body=body,
    )
    return Hit(email=email, score=9.0)


def test_answer_uses_retrieved_emails_as_context():
    hits = [_hit("m1", "Q3 planning", "The planning doc is due Friday.")]
    fake = FakeLLM()
    result = answer_question("When is the Q3 doc due?", hits, fake)

    assert isinstance(result, Answer)
    assert result.text == "The doc is due Friday [1]."
    assert result.sources == hits
    # The retrieved email is delimited in the prompt as untrusted context.
    assert "<emails>" in fake.user and "The planning doc is due Friday." in fake.user
    assert "Q3 doc due" in fake.user


def test_answer_prompt_marks_content_untrusted():
    assert "UNTRUSTED DATA" in QA_SYSTEM_PROMPT


def test_no_hits_short_circuits_without_calling_the_llm():
    class Boom(LLMClient):
        def complete(self, *, system, user, max_tokens=512):
            raise AssertionError("LLM must not be called when there are no hits")

    result = answer_question("anything", [], Boom())
    assert result.sources == []
    assert "don't have an email" in result.text


@pytest.mark.parametrize(
    ("base_url", "local"),
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:1234/v1", True),
        ("http://ollama.local/v1", True),
        ("https://api.groq.com/openai/v1", False),
        ("https://generativelanguage.googleapis.com/v1beta/openai/", False),
        ("", False),
    ],
)
def test_is_local_llm(base_url, local):
    assert is_local_llm(base_url) is local


def test_ask_answer_refuses_a_cloud_llm_without_allow(tmp_path, monkeypatch):
    """The privacy guard fails closed *before* any network call."""
    from typer.testing import CliRunner

    from inbox_agent.cli import app
    from inbox_agent.config import get_settings

    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    get_settings.cache_clear()  # bust the lru_cache so the env above is read

    runner = CliRunner()
    corpus, golden, db = tmp_path / "c.jsonl", tmp_path / "g.jsonl", tmp_path / "i.db"
    runner.invoke(app, ["generate-data", "--corpus", str(corpus), "--golden", str(golden)])
    runner.invoke(app, ["ingest", "--corpus", str(corpus), "--db", str(db)])

    result = runner.invoke(app, ["ask", "Q3 planning doc", "--answer", "--db", str(db)])
    get_settings.cache_clear()  # don't leak the cloud settings to other tests

    assert result.exit_code == 1
    assert "non-local LLM" in result.output


def test_triage_llm_refuses_a_cloud_llm_without_allow(tmp_path, monkeypatch):
    """Same guard on the triage path: real mail can't reach a cloud model."""
    from typer.testing import CliRunner

    from inbox_agent.cli import app
    from inbox_agent.config import get_settings

    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    get_settings.cache_clear()

    runner = CliRunner()
    corpus, golden, db = tmp_path / "c.jsonl", tmp_path / "g.jsonl", tmp_path / "i.db"
    runner.invoke(app, ["generate-data", "--corpus", str(corpus), "--golden", str(golden)])
    runner.invoke(app, ["ingest", "--corpus", str(corpus), "--db", str(db)])

    result = runner.invoke(app, ["triage", "--backend", "llm", "--db", str(db)])
    get_settings.cache_clear()

    assert result.exit_code == 1
    assert "non-local LLM" in result.output
