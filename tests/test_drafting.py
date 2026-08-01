"""Reply drafting. LLM mocked — no network, nothing sent."""

from __future__ import annotations

import pytest

from inbox_agent.drafting import DRAFT_SYSTEM_PROMPT, draft_reply
from inbox_agent.llm import LLMClient
from inbox_agent.models import Email


class FakeLLM(LLMClient):
    def __init__(self, reply="Thanks, Friday works for me."):
        self.reply = reply
        self.model = "fake"
        self.system = self.user = ""

    def complete(self, *, system, user, max_tokens=512):
        self.system, self.user = system, user
        return self.reply


def _email(body="Can we meet Friday?"):
    return Email(
        message_id="m1",
        thread_id="t1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="priya@x.example.com",
        from_name="Priya",
        subject="Meeting",
        body=body,
    )


def test_draft_uses_the_email_as_context():
    fake = FakeLLM()
    out = draft_reply(_email(), fake)
    assert out == "Thanks, Friday works for me."
    assert "Meeting" in fake.user and "Can we meet Friday?" in fake.user


def test_guidance_is_included():
    fake = FakeLLM()
    draft_reply(_email(), fake, guidance="politely decline")
    assert "politely decline" in fake.user


def test_prompt_marks_the_email_untrusted():
    assert "UNTRUSTED DATA" in DRAFT_SYSTEM_PROMPT


fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inbox_agent.config import get_settings  # noqa: E402
from inbox_agent.store import open_repository  # noqa: E402
from inbox_agent.synthetic import generate_corpus  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many(generate_corpus())
    repo.close()
    monkeypatch.setenv("DB_PATH", str(db))
    get_settings.cache_clear()
    from inbox_agent import api

    monkeypatch.setattr(api, "_chat_client", lambda: FakeLLM("Got it, thanks."))
    yield TestClient(api.app)
    get_settings.cache_clear()


def test_draft_endpoint_returns_a_draft(client):
    listing = client.get("/api/emails").json()["emails"]
    r = client.post(f"/api/emails/{listing[0]['id']}/draft", json={})
    assert r.status_code == 200
    assert r.json()["draft"] == "Got it, thanks."


def test_draft_unknown_email_is_404(client):
    assert client.post("/api/emails/nope/draft", json={}).status_code == 404


def test_draft_refuses_a_cloud_llm(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many(generate_corpus())
    repo.close()
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    get_settings.cache_clear()
    from inbox_agent import api

    listing = TestClient(api.app).get("/api/emails").json()["emails"]
    r = TestClient(api.app).post(f"/api/emails/{listing[0]['id']}/draft", json={})
    get_settings.cache_clear()
    assert r.status_code == 400
    assert "local" in r.json()["detail"].lower()
