"""Synthetic is the default; Gmail is opt-in, read-only, and parses correctly."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest

from inbox_agent.email_source import (
    GmailEmailSource,
    GmailNotConfigured,
    SyntheticEmailSource,
    _decode_b64,
    _extract_body,
    _html_to_text,
    _message_to_email,
    build_email_source,
)
from inbox_agent.synthetic import generate_corpus, write_corpus


def test_synthetic_source_reads_a_corpus_file(tmp_path):
    corpus, golden = tmp_path / "corpus.jsonl", tmp_path / "labels.jsonl"
    write_corpus(generate_corpus(), corpus_path=corpus, golden_path=golden)
    assert list(SyntheticEmailSource(corpus).fetch()) == generate_corpus()


def test_synthetic_source_generates_when_the_file_is_missing(tmp_path):
    source = SyntheticEmailSource(tmp_path / "missing.jsonl")
    assert list(source.fetch()) == generate_corpus()


def test_synthetic_source_respects_limit(tmp_path):
    assert len(list(SyntheticEmailSource(tmp_path / "missing.jsonl").fetch(limit=5))) == 5


def test_factory_defaults_to_synthetic():
    assert isinstance(build_email_source(), SyntheticEmailSource)


def test_factory_rejects_unknown_source():
    with pytest.raises(ValueError, match="unknown email source"):
        build_email_source("imap")


def test_gmail_refuses_destructive_full_scope():
    from pathlib import Path

    from inbox_agent.email_source import gmail_service

    # Read/write is allowed now, but the full-mailbox (delete) scope never is.
    with pytest.raises(GmailNotConfigured, match="destructive"):
        gmail_service(Path("x"), Path("y"), ["https://mail.google.com/"])


def test_gmail_is_inert_without_credentials(tmp_path):
    """Fetching without deps or creds fails loudly, and touches no network."""
    source = GmailEmailSource(
        credentials_path=tmp_path / "credentials.json",
        token_path=tmp_path / "token.json",
    )
    with pytest.raises(GmailNotConfigured):
        list(source.fetch())


# --- Gmail payload parsing (pure, offline) ---------------------------------


def _b64url(text: str) -> str:
    """URL-safe base64 with padding stripped, exactly as Gmail returns it."""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _gmail_message(msg_id: str, *, encoded_subject: bool = False, html_only: bool = False) -> dict:
    subject = "Weekly sync"
    if encoded_subject:
        subject = "=?UTF-8?B?" + base64.b64encode("Café ☕".encode()).decode() + "?="
    parts = [{"mimeType": "text/html", "body": {"data": _b64url("<p>Hello</p>")}}]
    if not html_only:
        parts.insert(0, {"mimeType": "text/plain", "body": {"data": _b64url("This is the body.")}})
    return {
        "id": msg_id,
        "threadId": f"t-{msg_id}",
        "internalDate": "1720000000000",
        "labelIds": ["INBOX", "IMPORTANT"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Alice Example <alice@example.com>"},
                {"name": "To", "value": "you@example.com, Bob <bob@example.net>"},
                {"name": "Cc", "value": "carol@example.org"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Thu, 03 Jul 2026 09:00:00 -0700"},
            ],
            "parts": parts,
        },
    }


def test_decode_b64_handles_missing_padding():
    assert _decode_b64(_b64url("hi there")) == "hi there"
    assert _decode_b64(None) == ""


def test_message_to_email_maps_all_fields():
    email = _message_to_email(_gmail_message("m1"))
    assert email.message_id == "m1"
    assert email.thread_id == "t-m1"
    assert email.from_addr == "alice@example.com"
    assert email.from_name == "Alice Example"
    assert email.to == ["you@example.com", "bob@example.net"]
    assert email.cc == ["carol@example.org"]
    assert email.subject == "Weekly sync"
    assert email.body == "This is the body."  # text/plain preferred over text/html
    assert email.labels == ["INBOX", "IMPORTANT"]
    assert email.category is None  # real mail has no ground truth
    assert email.date == datetime.fromtimestamp(1720000000, tz=UTC).isoformat()


def test_message_to_email_decodes_encoded_subject():
    email = _message_to_email(_gmail_message("m1", encoded_subject=True))
    assert email.subject == "Café ☕"


def test_extract_body_strips_html_when_no_plain_text():
    payload = _gmail_message("m1", html_only=True)["payload"]
    assert _extract_body(payload) == "Hello"  # tags stripped, not raw markup


def test_html_to_text_strips_tags_and_drops_script_style():
    html = (
        "<style>.x{color:red}</style><div>Hi <b>Alice</b>,</div>"
        "<p>Your order shipped.</p><script>evil()</script>"
    )
    text = _html_to_text(html)
    assert "Hi Alice," in text
    assert "Your order shipped." in text
    assert "color:red" not in text and "evil()" not in text
    assert "<" not in text and ">" not in text


def test_html_to_text_decodes_entities():
    assert _html_to_text("<p>Tom &amp; Jerry &lt;3</p>") == "Tom & Jerry <3"


# --- Gmail fetch loop (fake service; no OAuth, no network) ------------------


class _FakeExec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _FakeMessages:
    def __init__(self, pages, messages):
        self._pages = list(pages)
        self._messages = messages
        self.got = []

    def list(self, **_kwargs):
        return _FakeExec(self._pages.pop(0))

    def get(self, *, userId, id, format):
        self.got.append(id)
        return _FakeExec(self._messages[id])


class _FakeService:
    def __init__(self, messages_api):
        self._messages_api = messages_api

    def users(self):
        return self

    def messages(self):
        return self._messages_api


def _gmail_source_with(pages, message_ids):
    messages = {mid: _gmail_message(mid) for mid in message_ids}
    api = _FakeMessages(pages, messages)
    source = GmailEmailSource(service_factory=lambda: _FakeService(api))
    return source, api


def test_gmail_fetch_maps_messages_across_pages():
    pages = [
        {"messages": [{"id": "m1"}, {"id": "m2"}], "nextPageToken": "p2"},
        {"messages": [{"id": "m3"}]},
    ]
    source, api = _gmail_source_with(pages, ["m1", "m2", "m3"])
    emails = list(source.fetch())
    assert [e.message_id for e in emails] == ["m1", "m2", "m3"]
    assert api.got == ["m1", "m2", "m3"]  # paginated through both pages


def test_gmail_fetch_respects_limit_and_stops_early():
    pages = [
        {"messages": [{"id": "m1"}, {"id": "m2"}], "nextPageToken": "p2"},
        {"messages": [{"id": "m3"}]},
    ]
    source, api = _gmail_source_with(pages, ["m1", "m2", "m3"])
    emails = list(source.fetch(limit=2))
    assert [e.message_id for e in emails] == ["m1", "m2"]
    assert api.got == ["m1", "m2"]  # never fetched m3, never requested page 2
