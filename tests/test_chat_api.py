"""Chat API: persistence, citations, and the local-LLM privacy guard.

No network — the LLM client is faked. A temp DB per test.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inbox_agent.config import get_settings  # noqa: E402
from inbox_agent.llm import LLMClient  # noqa: E402
from inbox_agent.store import open_repository  # noqa: E402
from inbox_agent.synthetic import generate_corpus  # noqa: E402


class FakeLLM(LLMClient):
    model = "fake"

    def complete(self, *, system, user, max_tokens=512):
        return "Here is what I found [1]."


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many(generate_corpus())
    repo.close()

    monkeypatch.setenv("DB_PATH", str(db))
    get_settings.cache_clear()
    from inbox_agent import api

    # Force a local fake LLM so chat runs deterministically, offline.
    monkeypatch.setattr(api, "_chat_client", lambda: FakeLLM())
    yield TestClient(api.app)
    get_settings.cache_clear()


def test_chat_answers_and_returns_citations(client):
    r = client.post("/api/chat", json={"message": "when is the Q3 planning doc due"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Here is what I found [1]."
    assert body["chat_id"]
    assert body["citations"] and "id" in body["citations"][0]


def test_conversation_is_persisted_and_resumable(client):
    first = client.post("/api/chat", json={"message": "hello inbox"}).json()
    chat_id = first["chat_id"]
    client.post("/api/chat", json={"message": "anything about vendors", "chat_id": chat_id})

    listed = client.get("/api/chats").json()["chats"]
    assert any(c["id"] == chat_id for c in listed)

    history = client.get(f"/api/chats/{chat_id}").json()["messages"]
    # two turns -> two user + two assistant messages, in order
    roles = [m["role"] for m in history]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_count_question_uses_tools(client):
    r = client.post("/api/chat", json={"message": "how many emails from Priya"}).json()
    assert r["kind"] == "count"
    assert r["reply"].startswith("You have")


def test_action_stars_emails_and_persists(client):
    r = client.post("/api/chat", json={"message": "star all emails from Priya"}).json()
    assert r["kind"] == "action"
    assert "Starred" in r["reply"]
    starred = client.get("/api/emails", params={"starred": "true"}).json()
    assert starred["count"] >= 1


def test_empty_message_is_rejected(client):
    assert client.post("/api/chat", json={"message": "   "}).status_code == 400


def test_unknown_chat_id_is_404(client):
    r = client.post("/api/chat", json={"message": "hi", "chat_id": "nope"})
    assert r.status_code == 404


def test_history_for_unknown_chat_is_404(client):
    assert client.get("/api/chats/nope").status_code == 404


def test_chat_refuses_a_cloud_llm(tmp_path, monkeypatch):
    """The real guard: a non-local LLM must be refused before any inbox leaves."""
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

    r = TestClient(api.app).post("/api/chat", json={"message": "hi"})
    get_settings.cache_clear()

    assert r.status_code == 400
    assert "local" in r.json()["detail"].lower()
    # nothing was persisted, since the guard fired before any state change
    assert TestClient(api.app).get("/api/chats").json()["chats"] == []
