"""Where emails come from, behind one interface.

``SyntheticEmailSource`` is the default and needs nothing. ``GmailEmailSource``
is an opt-in, **read-only** source: it refuses any scope other than
``gmail.readonly``, so it can never modify or delete mail.

The Gmail code is split in two so it stays testable without a network:

* ``_message_to_email`` and its helpers are pure functions over a Gmail API
  payload — unit-tested offline against canned messages.
* ``GmailEmailSource.fetch`` walks the list/get API. Tests inject a fake service
  via ``service_factory`` to exercise the loop and pagination with no network.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from inbox_agent.models import Email
from inbox_agent.obs import get_logger
from inbox_agent.synthetic import DEFAULT_CORPUS_PATH, generate_corpus, load_corpus

_log = get_logger("email_source")

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class EmailSource(ABC):
    """A read-only source of emails."""

    name: str = "email-source"

    @abstractmethod
    def fetch(self, limit: int | None = None) -> Iterator[Email]:
        """Yield emails, at most ``limit`` if given. Must never mutate the source."""


class SyntheticEmailSource(EmailSource):
    """Fake emails from a corpus file, or generated if the file is absent."""

    name = "synthetic"

    def __init__(self, corpus_path: Path | None = DEFAULT_CORPUS_PATH) -> None:
        self.corpus_path = corpus_path

    def fetch(self, limit: int | None = None) -> Iterator[Email]:
        if self.corpus_path and Path(self.corpus_path).exists():
            emails = load_corpus(self.corpus_path)
        else:
            emails = generate_corpus()
        yield from emails[:limit] if limit else emails


class GmailNotConfigured(RuntimeError):
    """The Gmail path was used without its optional deps or credentials."""


class GmailEmailSource(EmailSource):
    """Opt-in, read-only Gmail source.

    Setup (you provide the credentials; they live only in git-ignored ``var/``):

    1. Create a Google Cloud project and enable the **Gmail API**.
    2. Configure an OAuth consent screen and add yourself as a test user.
    3. Create an OAuth client ID of type *Desktop app* and download the JSON.
    4. Save it to ``var/credentials.json`` (or set ``GMAIL_CREDENTIALS_PATH``).
       The cached token goes to ``var/token.json``. Both are git-ignored.
    5. Install the optional dependencies: ``uv sync --extra gmail``

    The first fetch opens a browser once to grant **read-only** access; the
    token is cached so later runs are non-interactive.

    Privacy: once a real inbox is connected, switch the LLM to a local model
    (Ollama) or a documented no-training provider. Real email must never be
    sent to a free tier that trains on prompts.

    TODO(phase-3): trust-label fetched content before it reaches any tool.
    """

    name = "gmail"

    def __init__(
        self,
        credentials_path: Path = Path("var/credentials.json"),
        token_path: Path = Path("var/token.json"),
        scope: str = READONLY_SCOPE,
        service_factory: Callable[[], object] | None = None,
    ) -> None:
        # Hard guarantee: this class is read-only.
        if scope != READONLY_SCOPE:
            raise GmailNotConfigured(
                f"This project is read-only; refusing scope {scope!r}. "
                f"Only {READONLY_SCOPE!r} is permitted."
            )
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.scope = scope
        # Injected by tests to bypass OAuth/network; None means build the real one.
        self._service_factory = service_factory

    def fetch(self, limit: int | None = None) -> Iterator[Email]:
        """Yield up to ``limit`` messages, newest first (read-only)."""
        service = (self._service_factory or self._authorized_service)()
        _log.info("gmail: fetching (limit=%s, read-only)", limit)

        yielded = 0
        page_token: str | None = None
        while True:
            page_size = 100 if limit is None else min(100, limit - yielded)
            params = {"userId": "me", "maxResults": page_size}
            if page_token:
                params["pageToken"] = page_token
            listing = service.users().messages().list(**params).execute()

            for meta in listing.get("messages", []):
                raw = (
                    service.users()
                    .messages()
                    .get(userId="me", id=meta["id"], format="full")
                    .execute()
                )
                yield _message_to_email(raw)
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

            page_token = listing.get("nextPageToken")
            if not page_token:
                return

    def _authorized_service(self):
        """Build an authorized, read-only Gmail API client (does OAuth if needed)."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GmailNotConfigured(
                "The Gmail source needs optional dependencies:\n"
                "    uv sync --extra gmail\n"
                "The synthetic source (the default) needs none of this."
            ) from exc

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), [self.scope])

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise GmailNotConfigured(
                        f"No OAuth client credentials at {self.credentials_path}. "
                        "See GmailEmailSource's docstring for the one-time setup."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), [self.scope]
                )
                creds = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        return build("gmail", "v1", credentials=creds, cache_discovery=False)


# --- pure transform: Gmail API payload -> Email (unit-tested, no network) ---


def _decode_words(value: str) -> str:
    """Decode RFC 2047 encoded-words (e.g. ``=?UTF-8?B?...?=``) to plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (ValueError, LookupError):
        return value


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_b64(data: str | None) -> str:
    """Decode Gmail's URL-safe base64 body data (padding is often missing)."""
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _find_mime(payload: dict, target: str) -> str | None:
    """Depth-first search for the first part whose mimeType starts with ``target``."""
    if payload.get("mimeType", "").startswith(target):
        return _decode_b64(payload.get("body", {}).get("data"))
    for part in payload.get("parts", []) or []:
        found = _find_mime(part, target)
        if found is not None:
            return found
    return None


class _HTMLToText(HTMLParser):
    """Collapse HTML into readable plain text (block tags become line breaks)."""

    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
    _SKIP = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entities decode into data for us
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = [ln.strip() for ln in "".join(self._parts).splitlines()]
        return "\n".join(ln for ln in lines if ln).strip()


def _html_to_text(html: str) -> str:
    """Best-effort HTML -> text. Returns the input unchanged if parsing fails."""
    parser = _HTMLToText()
    try:
        parser.feed(html)
    except Exception:  # never let a malformed email break ingestion
        return html
    return parser.text() or html


def _extract_body(payload: dict) -> str:
    """Best-effort body text: prefer text/plain, then text/html (stripped)."""
    plain = _find_mime(payload, "text/plain")
    if plain and plain.strip():
        return plain.strip()
    html = _find_mime(payload, "text/html")
    if html and html.strip():
        return _html_to_text(html)
    raw = _decode_b64(payload.get("body", {}).get("data"))
    return _html_to_text(raw) if "<" in raw and ">" in raw else raw


def _date_iso(raw: dict, headers: list[dict]) -> str:
    """Normalize a message timestamp to ISO 8601, matching the synthetic corpus.

    Prefer Gmail's ``internalDate`` (epoch ms); fall back to the Date header.
    """
    internal = raw.get("internalDate")
    if internal:
        return datetime.fromtimestamp(int(internal) / 1000, tz=UTC).isoformat()
    date_header = _header(headers, "Date")
    if date_header:
        try:
            return parsedate_to_datetime(date_header).isoformat()
        except (TypeError, ValueError):
            pass
    return date_header


def _message_to_email(raw: dict) -> Email:
    """Map a Gmail ``messages.get`` (format="full") result to our Email.

    ``category`` is None — real mail has no ground-truth label.
    """
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])
    from_name, from_addr = parseaddr(_header(headers, "From"))
    return Email(
        message_id=raw.get("id", ""),
        thread_id=raw.get("threadId", ""),
        date=_date_iso(raw, headers),
        from_addr=from_addr,
        from_name=_decode_words(from_name),
        to=[addr for _, addr in getaddresses([_header(headers, "To")]) if addr],
        cc=[addr for _, addr in getaddresses([_header(headers, "Cc")]) if addr],
        subject=_decode_words(_header(headers, "Subject")),
        body=_extract_body(payload),
        labels=raw.get("labelIds", []),
        category=None,
    )


def build_email_source(kind: str = "synthetic", *, corpus_path: Path | None = None) -> EmailSource:
    """Return the email source named by ``kind`` ("synthetic" | "gmail")."""
    if kind == "synthetic":
        return SyntheticEmailSource(corpus_path or DEFAULT_CORPUS_PATH)
    if kind == "gmail":
        from inbox_agent.config import get_settings

        settings = get_settings()
        return GmailEmailSource(
            credentials_path=settings.gmail_credentials_path,
            token_path=settings.gmail_token_path,
            scope=settings.gmail_scope,
        )
    raise ValueError(f"unknown email source: {kind!r} (expected 'synthetic' or 'gmail')")
