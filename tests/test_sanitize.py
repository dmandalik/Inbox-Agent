"""HTML sanitization + body_html storage and serving."""

from __future__ import annotations

import pytest

from inbox_agent.models import Email
from inbox_agent.sanitize import sanitize_html
from inbox_agent.store import open_repository


def test_strips_scripts_and_handlers_keeps_formatting():
    dirty = (
        '<p style="color:red">Hi <b>there</b></p>'
        "<script>alert(1)</script>"
        '<a href="javascript:evil()" onclick="x()">link</a>'
    )
    out = sanitize_html(dirty)
    assert "<script" not in out
    assert "javascript:" not in out
    assert "onclick" not in out
    assert "<b>there</b>" in out
    assert "color:red" in out  # inline styles preserved


def test_empty_input_returns_empty():
    assert sanitize_html("") == ""
    assert sanitize_html("   ") == ""


def _email(mid, html):
    return Email(
        message_id=mid,
        thread_id="t1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="a@x.example.com",
        from_name="A",
        subject="s",
        body="plain text",
        body_html=html,
    )


def test_body_html_round_trips_through_store():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1", "<p>hello</p>")])
    assert repo.get("m1").body_html == "<p>hello</p>"


def test_migration_adds_body_html_to_old_db(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE emails (message_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, "
        "date TEXT NOT NULL, from_addr TEXT NOT NULL, from_name TEXT DEFAULT '', "
        "to_json TEXT DEFAULT '[]', cc_json TEXT DEFAULT '[]', subject TEXT DEFAULT '', "
        "body TEXT DEFAULT '', labels_json TEXT DEFAULT '[]', category TEXT)"
    )
    conn.commit()
    conn.close()
    repo = open_repository(str(db))  # migration runs on open
    repo.add_many([_email("m1", "<b>hi</b>")])
    assert repo.get("m1").body_html == "<b>hi</b>"


fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inbox_agent.config import get_settings  # noqa: E402


def test_api_serves_sanitized_html(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many([_email("m1", "<p>hi</p><script>alert(1)</script>")])
    repo.close()
    monkeypatch.setenv("DB_PATH", str(db))
    get_settings.cache_clear()
    from inbox_agent import api

    body_html = TestClient(api.app).get("/api/emails/m1").json()["body_html"]
    get_settings.cache_clear()
    assert "<p>hi</p>" in body_html
    assert "<script" not in body_html
