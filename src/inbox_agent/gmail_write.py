"""Gmail write actions — send a reply, mark a message read.

This is the one part of the app that *writes* to Gmail. It uses the same OAuth
token as the read path (authorized for ``gmail.modify`` + ``gmail.send``). Two
narrow actions only:

* :meth:`GmailWriter.send_reply` — send a reply in the original thread.
* :meth:`GmailWriter.mark_read` — remove the UNREAD label (sync read-state).

Sending is always a deliberate, user-confirmed action in the UI; nothing here
sends on its own. There is no delete path, and the destructive full-mailbox
scope is refused in :func:`email_source.gmail_service`.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from email.mime.text import MIMEText
from functools import lru_cache
from pathlib import Path

from inbox_agent.email_source import gmail_service
from inbox_agent.models import Email


@lru_cache(maxsize=1)
def _service_cached(creds: str, token: str, scopes: tuple[str, ...]):
    # Cached so we build the Gmail client (and its discovery doc) once, not per
    # request — matters because read-state sync calls this on every email open.
    return gmail_service(Path(creds), Path(token), list(scopes))


class GmailWriter:
    """Sends replies and updates read-state for one Gmail account."""

    def __init__(
        self,
        credentials_path: Path,
        token_path: Path,
        scopes: list[str],
        service_factory: Callable[[], object] | None = None,
    ) -> None:
        self._cp = str(credentials_path)
        self._tp = str(token_path)
        self._scopes = tuple(scopes)
        self._factory = service_factory  # tests inject a fake service

    def _service(self):
        if self._factory is not None:
            return self._factory()
        return _service_cached(self._cp, self._tp, self._scopes)

    def send_reply(self, email: Email, body: str) -> str:
        """Send ``body`` as a reply to ``email``, kept in the same thread."""
        msg = MIMEText(body)
        msg["To"] = email.from_addr
        subject = email.subject or ""
        msg["Subject"] = subject if subject[:3].lower() == "re:" else f"Re: {subject}"
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        payload: dict = {"raw": raw}
        if email.thread_id:
            payload["threadId"] = email.thread_id
        sent = self._service().users().messages().send(userId="me", body=payload).execute()
        return sent.get("id", "")

    def mark_read(self, message_id: str) -> None:
        """Clear the UNREAD label on a message (idempotent)."""
        self._service().users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()


def build_gmail_writer(settings=None) -> GmailWriter:
    from inbox_agent.config import get_settings

    s = settings or get_settings()
    return GmailWriter(s.gmail_credentials_path, s.gmail_token_path, s.gmail_scopes)
