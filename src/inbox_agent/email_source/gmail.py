"""Read-only Gmail source — OPTIONAL, opt-in, and never required to run.

This is a guarded stub for Phase 0's real-inbox path. It is intentionally
inert unless you (a) install the extra and (b) provide your own OAuth
credentials — nothing here can run against a real account by accident, and only
the ``gmail.readonly`` scope is ever requested (no send/delete/modify).

Setup (you do this yourself; never paste secrets into chat):

1. Create a Google Cloud project and enable the **Gmail API**.
   https://console.cloud.google.com/  →  APIs & Services → Enable APIs
2. Configure an OAuth consent screen (External, testing is fine) and add your
   own address as a test user.
3. Create an **OAuth client ID** of type *Desktop app*; download the JSON.
4. Save it to the git-ignored path ``var/credentials.json`` (or set
   ``GMAIL_CREDENTIALS_PATH``). The token cache goes to ``var/token.json``.
5. Install the optional dependencies::

       uv sync --extra gmail

6. Use it explicitly (the synthetic source remains the default everywhere else).

Privacy: once a real inbox is connected, switch the LLM to a local model
(Ollama) or a documented no-training provider — real email must never be sent
to a free tier that trains on prompts. See README / AGENTS.md.

TODO(phase-0): token refresh edge cases, pagination tuning, HTML→text cleanup.
TODO(phase-3): trust-labeling of fetched content before it reaches any tool.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from pathlib import Path

from inbox_agent.email_source.base import EmailSource
from inbox_agent.models import Email
from inbox_agent.obs import get_logger

_log = get_logger("email_source.gmail")

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailNotConfigured(RuntimeError):
    """Raised when the Gmail path is used without its deps or credentials."""


def _require_google_libs():
    """Import the Google client libs lazily, with an actionable error."""
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise GmailNotConfigured(
            "The Gmail source needs optional dependencies. Install them with:\n"
            "    uv sync --extra gmail\n"
            "The synthetic source (default) needs none of this."
        ) from exc
    return build, Credentials, InstalledAppFlow, Request


class GmailEmailSource(EmailSource):
    """Read-only Gmail source (opt-in). Requests only ``gmail.readonly``."""

    name = "gmail"

    def __init__(
        self,
        credentials_path: Path = Path("var/credentials.json"),
        token_path: Path = Path("var/token.json"),
        scope: str = READONLY_SCOPE,
    ) -> None:
        # Hard guarantee: this class is read-only. Reject any non-read scope.
        if scope != READONLY_SCOPE:
            raise GmailNotConfigured(
                f"Milestone 1 is read-only; refusing scope {scope!r}. "
                f"Only {READONLY_SCOPE!r} is permitted."
            )
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.scope = scope

    def _credentials(self):
        """Load or run the OAuth flow, caching a token under ``var/``."""
        _build, Credentials, InstalledAppFlow, Request = _require_google_libs()
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), [self.scope])
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not self.credentials_path.exists():
                raise GmailNotConfigured(
                    f"No OAuth client secret at {self.credentials_path}. "
                    "See the setup steps in this module's docstring; the file is "
                    "yours to create and stays git-ignored under var/."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), [self.scope]
            )
            creds = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json())
        return creds

    def fetch(self, limit: int | None = None) -> Iterable[Email]:
        """Yield up to ``limit`` messages from the authenticated inbox (read-only)."""
        build, *_ = _require_google_libs()
        creds = self._credentials()
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        _log.info("gmail.fetch start limit=%s scope=%s", limit, self.scope)

        listing = service.users().messages().list(userId="me", maxResults=limit or 100).execute()
        for meta in listing.get("messages", []):
            raw = (
                service.users().messages().get(userId="me", id=meta["id"], format="full").execute()
            )
            yield _message_to_email(raw)


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """Best-effort plain-text extraction from a Gmail payload."""
    if payload.get("mimeType", "").startswith("text/plain"):
        return _decode_part(payload)
    for part in payload.get("parts", []) or []:
        if part.get("mimeType", "").startswith("text/plain"):
            return _decode_part(part)
    # Fall back to whatever the top-level body holds.
    return _decode_part(payload)


def _message_to_email(raw: dict) -> Email:
    """Map a Gmail ``messages.get`` result to our :class:`Email`. category=None."""
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])
    to_field = _header(headers, "To")
    cc_field = _header(headers, "Cc")
    return Email(
        message_id=raw.get("id", ""),
        thread_id=raw.get("threadId", ""),
        date=_header(headers, "Date"),
        from_addr=_header(headers, "From"),
        from_name=_header(headers, "From"),
        to=[a.strip() for a in to_field.split(",") if a.strip()],
        cc=[a.strip() for a in cc_field.split(",") if a.strip()],
        subject=_header(headers, "Subject"),
        body=_extract_body(payload),
        labels=raw.get("labelIds", []),
        category=None,  # real mail has no ground-truth label
    )
