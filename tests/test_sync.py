"""Live Gmail sync endpoint. Gmail is faked — no network."""

from __future__ import annotations

import pytest

from inbox_agent.email_source import GmailNotConfigured
from inbox_agent.models import Email

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inbox_agent.config import get_settings  # noqa: E402
from inbox_agent.store import open_repository  # noqa: E402


def _email(mid: str) -> Email:
    return Email(
        message_id=mid,
        thread_id="t-" + mid,
        date="2026-06-15T09:00:00+00:00",
        from_addr="a@x.example.com",
        from_name="Sender",
        subject="hi",
        body="hello",
    )


class FakeSource:
    name = "gmail"

    def __init__(self, emails):
        self._emails = emails

    def fetch(self, limit=None):
        return iter(self._emails[:limit] if limit else self._emails)


def _client(tmp_path, monkeypatch, source):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many([_email("m1")])
    repo.set_state("m1", read=True)  # local state we must preserve across sync
    repo.close()
    monkeypatch.setenv("DB_PATH", str(db))
    get_settings.cache_clear()
    from inbox_agent import api

    monkeypatch.setattr(api, "build_email_source", lambda kind: source)
    return TestClient(api.app)


def test_sync_adds_new_and_preserves_state(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, FakeSource([_email("m1"), _email("m2")]))
    r = client.post("/api/sync", json={}).json()
    assert r["added"] == 1  # m2 is new; m1 already present
    assert r["fetched"] == 2
    # re-ingesting m1 must not wipe its read flag
    assert client.get("/api/emails/m1").json()["read"] is True
    get_settings.cache_clear()


def test_sync_reports_gmail_not_configured(tmp_path, monkeypatch):
    class Missing:
        name = "gmail"

        def fetch(self, limit=None):
            raise GmailNotConfigured("no token")

    client = _client(tmp_path, monkeypatch, Missing())
    r = client.post("/api/sync", json={})
    assert r.status_code == 400
    get_settings.cache_clear()
