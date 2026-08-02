"""Gmail write: reply sending, read-state sync, and the API. No network."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from inbox_agent.gmail_write import GmailWriter
from inbox_agent.models import Email


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _Messages:
    def __init__(self, calls):
        self.calls = calls

    def send(self, userId, body):
        self.calls.append(("send", body))
        return _Exec({"id": "sent1"})

    def modify(self, userId, id, body):
        self.calls.append(("modify", id, body))
        return _Exec({})


class FakeService:
    def __init__(self):
        self.calls = []
        self._users = type("U", (), {"messages": lambda s: _Messages(self.calls)})()

    def users(self):
        return self._users


def _email(subject="Hello", thread="th1"):
    return Email(
        message_id="m1",
        thread_id=thread,
        date="2026-06-15T09:00:00+00:00",
        from_addr="alice@example.com",
        from_name="Alice",
        subject=subject,
        body="original",
    )


def _writer(svc):
    return GmailWriter(Path("c"), Path("t"), ["s"], service_factory=lambda: svc)


def test_send_reply_is_threaded_and_addressed():
    svc = FakeService()
    sid = _writer(svc).send_reply(_email(), "my reply text")
    assert sid == "sent1"
    kind, body = svc.calls[0]
    assert kind == "send"
    assert body["threadId"] == "th1"
    raw = base64.urlsafe_b64decode(body["raw"]).decode()
    assert "To: alice@example.com" in raw
    assert "Subject: Re: Hello" in raw
    assert "my reply text" in raw


def test_send_reply_keeps_existing_re_prefix():
    svc = FakeService()
    _writer(svc).send_reply(_email(subject="Re: Hello"), "x")
    raw = base64.urlsafe_b64decode(svc.calls[0][1]["raw"]).decode()
    assert "Subject: Re: Hello" in raw
    assert "Re: Re:" not in raw


def test_mark_read_removes_unread_label():
    svc = FakeService()
    _writer(svc).mark_read("m1")
    assert svc.calls[0] == ("modify", "m1", {"removeLabelIds": ["UNREAD"]})


# --- API ----------------------------------------------------------------
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inbox_agent.config import get_settings  # noqa: E402
from inbox_agent.store import open_repository  # noqa: E402
from inbox_agent.synthetic import generate_corpus  # noqa: E402


class FakeWriter:
    def __init__(self):
        self.sent = None
        self.marked = []

    def send_reply(self, email, body):
        self.sent = (email.message_id, body)
        return "sent1"

    def mark_read(self, message_id):
        self.marked.append(message_id)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many(generate_corpus())
    repo.close()
    token = tmp_path / "token.json"
    token.write_text("{}")  # existence is what the guard checks
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(token))
    get_settings.cache_clear()
    from inbox_agent import api

    fake = FakeWriter()
    monkeypatch.setattr(api, "build_gmail_writer", lambda settings=None: fake)
    yield TestClient(api.app), fake
    get_settings.cache_clear()


def test_send_endpoint_sends_via_writer(ctx):
    client, fake = ctx
    mid = client.get("/api/emails").json()["emails"][0]["id"]
    r = client.post(f"/api/emails/{mid}/send", json={"body": "Thanks!"})
    assert r.status_code == 200
    assert r.json()["sent"] == "sent1"
    assert fake.sent == (mid, "Thanks!")


def test_send_empty_body_rejected(ctx):
    client, _ = ctx
    mid = client.get("/api/emails").json()["emails"][0]["id"]
    assert client.post(f"/api/emails/{mid}/send", json={"body": "  "}).status_code == 400


def test_send_unknown_email_404(ctx):
    client, _ = ctx
    assert client.post("/api/emails/nope/send", json={"body": "hi"}).status_code == 404


def test_marking_read_syncs_to_gmail(ctx):
    client, fake = ctx
    mid = client.get("/api/emails").json()["emails"][0]["id"]
    client.patch(f"/api/emails/{mid}/state", json={"read": True})
    assert fake.marked == [mid]


def test_send_without_token_is_400(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many(generate_corpus())
    repo.close()
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(tmp_path / "missing.json"))
    get_settings.cache_clear()
    from inbox_agent import api

    mid = TestClient(api.app).get("/api/emails").json()["emails"][0]["id"]
    r = TestClient(api.app).post(f"/api/emails/{mid}/send", json={"body": "hi"})
    get_settings.cache_clear()
    assert r.status_code == 400
    assert "authoriz" in r.json()["detail"].lower()
