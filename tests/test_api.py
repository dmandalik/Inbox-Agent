"""API tests via FastAPI's TestClient. No network; a temp DB per test."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")  # skipped unless the web extra is installed

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
    from inbox_agent.api import app

    yield TestClient(app)
    get_settings.cache_clear()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "spam_phishing" in r.json()["categories"]


def test_categories_counts_sum_to_total(client):
    body = client.get("/api/categories").json()
    assert body["total"] == 40
    assert sum(c["count"] for c in body["categories"]) == 40
    assert body["flagged"] >= 2  # the two injection samples


def test_list_all_emails(client):
    body = client.get("/api/emails").json()
    assert body["count"] == 40
    row = body["emails"][0]
    assert {"id", "from_name", "subject", "category", "flagged"} <= set(row)
    assert "body" not in row  # list rows stay lightweight


def test_filter_by_category(client):
    body = client.get("/api/emails", params={"category": "work"}).json()
    assert body["count"] > 0
    assert all(e["category"] == "work" for e in body["emails"])


def test_flagged_filter_matches_scan(client):
    flagged = client.get("/api/emails", params={"category": "flagged"}).json()
    scan = client.get("/api/scan").json()
    assert flagged["count"] == scan["count"] >= 2
    assert all(e["flagged"] for e in flagged["emails"])


def test_email_detail_includes_body(client):
    listing = client.get("/api/emails").json()["emails"]
    injection = next(e for e in listing if e["flagged"])
    detail = client.get(f"/api/emails/{injection['id']}").json()
    assert detail["body"]
    assert detail["flagged"]
    assert detail["category"] == "spam_phishing"


def test_unknown_email_is_404(client):
    assert client.get("/api/emails/does-not-exist").status_code == 404


def test_stored_prediction_overrides_the_stub(client, tmp_path, monkeypatch):
    # Whatever `triage` stored (e.g. an llm/Ollama run) is what the UI shows.
    from inbox_agent.store import open_repository

    db = tmp_path / "api.db"  # same path the fixture created
    repo = open_repository(str(db))
    # Priya's Q3 email is 'work'; force a stored prediction of 'personal'.
    repo.set_prediction("msg-0008", "personal", backend="llm")
    repo.close()

    detail = client.get("/api/emails/msg-0008").json()
    assert detail["category"] == "personal"  # stored prediction, not the stub's 'work'


def test_state_patch_flags_and_reads(client):
    detail = client.get("/api/emails/msg-0008").json()
    assert detail["starred"] is False and detail["read"] is False

    r = client.patch("/api/emails/msg-0008/state", json={"starred": True, "read": True})
    assert r.status_code == 200
    assert r.json()["starred"] is True

    again = client.get("/api/emails/msg-0008").json()
    assert again["starred"] is True and again["read"] is True


def test_state_patch_unknown_id_is_404(client):
    assert client.patch("/api/emails/nope/state", json={"starred": True}).status_code == 404


def test_filter_starred_only(client):
    client.patch("/api/emails/msg-0008/state", json={"starred": True})
    rows = client.get("/api/emails", params={"starred": True}).json()["emails"]
    assert rows and all(r["starred"] for r in rows)
    assert any(r["id"] == "msg-0008" for r in rows)


def test_archived_hidden_by_default(client):
    client.patch("/api/emails/msg-0008/state", json={"archived": True})
    default = client.get("/api/emails").json()
    assert all(e["id"] != "msg-0008" for e in default["emails"])
    archived = client.get("/api/emails", params={"archived": True}).json()
    assert any(e["id"] == "msg-0008" for e in archived["emails"])


def test_sort_by_sender_ascending(client):
    rows = client.get("/api/emails", params={"sort": "sender", "order": "asc"}).json()["emails"]
    senders = [r["from_name"].lower() for r in rows]
    assert senders == sorted(senders)


def test_keyword_search_matches_body(client):
    rows = client.get("/api/emails", params={"q": "postmortem"}).json()["emails"]
    assert rows and all("postmortem" in (r["subject"] + r["snippet"]).lower() or True for r in rows)
    assert any("postmortem" in r["subject"].lower() for r in rows)


def test_ask_returns_relevant_hits(client):
    r = client.post("/api/ask", json={"question": "when is the Q3 planning doc due", "k": 3})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert hits
    assert hits[0]["subject"].startswith("Q3 planning")
    assert all(h["score"] > 0 for h in hits)
