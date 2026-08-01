"""SQLite storage: schema + an idempotent repository.

The repository is the only place that touches SQL. Ground-truth ``category``
and the triage output (``predicted_*``) live in separate columns so a label and
a prediction can never be conflated.

Ingestion is idempotent: re-adding a ``message_id`` refreshes the source
columns but **preserves** any existing prediction.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from inbox_agent.models import Email

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    message_id         TEXT PRIMARY KEY,
    thread_id          TEXT NOT NULL,
    date               TEXT NOT NULL,
    from_addr          TEXT NOT NULL,
    from_name          TEXT NOT NULL DEFAULT '',
    to_json            TEXT NOT NULL DEFAULT '[]',
    cc_json            TEXT NOT NULL DEFAULT '[]',
    subject            TEXT NOT NULL DEFAULT '',
    body               TEXT NOT NULL DEFAULT '',
    labels_json        TEXT NOT NULL DEFAULT '[]',
    category           TEXT,   -- ground truth (synthetic mail only)
    predicted_category TEXT,   -- triage output
    predicted_backend  TEXT,   -- which classifier produced it
    predicted_at       TEXT,
    starred            INTEGER NOT NULL DEFAULT 0,  -- user flag/star
    read               INTEGER NOT NULL DEFAULT 0,  -- 0 = unread
    archived           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);

-- Immutable per-message summary cache. Email bodies never change, so a summary
-- is keyed by (message_id, prompt_version) and never needs content-based
-- invalidation; bump prompt_version to re-summarize on purpose.
CREATE TABLE IF NOT EXISTS summaries (
    message_id     TEXT PRIMARY KEY,
    summary        TEXT NOT NULL,
    model          TEXT NOT NULL DEFAULT '',
    prompt_version INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

-- Saved conversations. `summary` is a rolling digest of older turns so we never
-- re-send a whole transcript to the model (keeps per-turn cost flat).
CREATE TABLE IF NOT EXISTS chats (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id        TEXT NOT NULL,
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat ON chat_messages(chat_id, id);

-- User-defined, color-coded labels. `instructions` is a plain-English rule the
-- LLM uses to auto-apply the label ("anything about money, bills, invoices").
CREATE TABLE IF NOT EXISTS labels (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    color        TEXT NOT NULL DEFAULT '#2f6bea',
    instructions TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_labels (
    message_id TEXT NOT NULL,
    label_id   TEXT NOT NULL,
    PRIMARY KEY (message_id, label_id)
);
CREATE INDEX IF NOT EXISTS idx_email_labels_label ON email_labels(label_id);
CREATE INDEX IF NOT EXISTS idx_email_labels_msg ON email_labels(message_id);
"""

# User-set state columns, kept separate from ground truth and predictions.
# Names are fixed literals here (never user input), so interpolating them in
# SQL below is safe.
_STATE_COLUMNS = {
    "starred": "INTEGER NOT NULL DEFAULT 0",
    "read": "INTEGER NOT NULL DEFAULT 0",
    "archived": "INTEGER NOT NULL DEFAULT 0",
}


def _ensure_state_columns(conn: sqlite3.Connection) -> None:
    """Add any missing state columns to an existing DB (lightweight migration)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(emails)").fetchall()}
    for name, decl in _STATE_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE emails ADD COLUMN {name} {decl}")
    conn.commit()


# Columns written by ingestion. Prediction columns are absent on purpose:
# an upsert must never clobber them.
_SOURCE_COLUMNS = (
    "message_id",
    "thread_id",
    "date",
    "from_addr",
    "from_name",
    "to_json",
    "cc_json",
    "subject",
    "body",
    "labels_json",
    "category",
)


def _to_row(e: Email) -> dict:
    row = e.to_dict()
    for field in ("to", "cc", "labels"):
        row[f"{field}_json"] = json.dumps(row.pop(field))
    return row


def _to_email(row: sqlite3.Row) -> Email:
    return Email(
        message_id=row["message_id"],
        thread_id=row["thread_id"],
        date=row["date"],
        from_addr=row["from_addr"],
        from_name=row["from_name"],
        to=json.loads(row["to_json"]),
        cc=json.loads(row["cc_json"]),
        subject=row["subject"],
        body=row["body"],
        labels=json.loads(row["labels_json"]),
        category=row["category"],
    )


class EmailRepository:
    """Query + persistence surface for stored emails."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript(SCHEMA)
        _ensure_state_columns(self.conn)
        self.conn.commit()

    def add_many(self, emails: list[Email]) -> int:
        """Upsert emails. Idempotent: no duplicates, predictions preserved."""
        cols = ", ".join(_SOURCE_COLUMNS)
        values = ", ".join(f":{c}" for c in _SOURCE_COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _SOURCE_COLUMNS if c != "message_id")
        self.conn.executemany(
            f"INSERT INTO emails ({cols}) VALUES ({values}) "
            f"ON CONFLICT(message_id) DO UPDATE SET {updates}",
            [_to_row(e) for e in emails],
        )
        self.conn.commit()
        return len(emails)

    def add(self, email: Email) -> None:
        self.add_many([email])

    def get(self, message_id: str) -> Email | None:
        row = self.conn.execute(
            "SELECT * FROM emails WHERE message_id = ?", (message_id,)
        ).fetchone()
        return _to_email(row) if row else None

    def all(self) -> list[Email]:
        """All emails, newest first."""
        rows = self.conn.execute("SELECT * FROM emails ORDER BY date DESC, message_id").fetchall()
        return [_to_email(r) for r in rows]

    def by_thread(self, thread_id: str) -> list[Email]:
        """A thread's messages, oldest first. (Phase 2 chunks on this.)"""
        rows = self.conn.execute(
            "SELECT * FROM emails WHERE thread_id = ? ORDER BY date", (thread_id,)
        ).fetchall()
        return [_to_email(r) for r in rows]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0])

    def set_prediction(self, message_id: str, category: str, backend: str) -> None:
        cur = self.conn.execute(
            "UPDATE emails SET predicted_category=?, predicted_backend=?, predicted_at=? "
            "WHERE message_id=?",
            (category, backend, datetime.now(UTC).isoformat(), message_id),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"unknown message_id: {message_id}")

    def get_prediction(self, message_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT predicted_category FROM emails WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row["predicted_category"] if row else None

    def predictions(self) -> dict[str, str]:
        """message_id -> predicted_category, for rows that have one."""
        rows = self.conn.execute(
            "SELECT message_id, predicted_category FROM emails WHERE predicted_category IS NOT NULL"
        ).fetchall()
        return {r["message_id"]: r["predicted_category"] for r in rows}

    def ground_truth(self) -> dict[str, str]:
        """message_id -> ground-truth category, for rows that have one."""
        rows = self.conn.execute(
            "SELECT message_id, category FROM emails WHERE category IS NOT NULL"
        ).fetchall()
        return {r["message_id"]: r["category"] for r in rows}

    def prediction_backends(self) -> set[str]:
        """Distinct backends recorded across current predictions."""
        rows = self.conn.execute(
            "SELECT DISTINCT predicted_backend FROM emails WHERE predicted_backend IS NOT NULL"
        ).fetchall()
        return {r["predicted_backend"] for r in rows}

    # --- user state (starred / read / archived) ---------------------------
    def set_state(
        self,
        message_id: str,
        *,
        starred: bool | None = None,
        read: bool | None = None,
        archived: bool | None = None,
    ) -> None:
        """Update only the state fields that are provided. Others untouched."""
        updates = {"starred": starred, "read": read, "archived": archived}
        changes = {k: (1 if v else 0) for k, v in updates.items() if v is not None}
        if not changes:
            return
        assigns = ", ".join(f"{col}=?" for col in changes)  # cols are fixed literals
        params = [*changes.values(), message_id]
        cur = self.conn.execute(f"UPDATE emails SET {assigns} WHERE message_id=?", params)
        self.conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"unknown message_id: {message_id}")

    def _state_of(self, row: sqlite3.Row) -> dict[str, bool]:
        return {c: bool(row[c]) for c in _STATE_COLUMNS}

    def get_state(self, message_id: str) -> dict[str, bool] | None:
        cols = ", ".join(_STATE_COLUMNS)
        row = self.conn.execute(
            f"SELECT {cols} FROM emails WHERE message_id=?", (message_id,)
        ).fetchone()
        return self._state_of(row) if row else None

    def states(self) -> dict[str, dict[str, bool]]:
        """message_id -> {starred, read, archived} for every email."""
        cols = ", ".join(("message_id", *_STATE_COLUMNS))
        rows = self.conn.execute(f"SELECT {cols} FROM emails").fetchall()
        return {r["message_id"]: self._state_of(r) for r in rows}

    # --- summary cache (immutable, keyed by prompt_version) ----------------
    def get_summary(self, message_id: str, prompt_version: int = 1) -> str | None:
        """Cached summary for a message at this prompt_version, or None on miss."""
        row = self.conn.execute(
            "SELECT summary FROM summaries WHERE message_id=? AND prompt_version=?",
            (message_id, prompt_version),
        ).fetchone()
        return row["summary"] if row else None

    def set_summary(
        self, message_id: str, summary: str, *, model: str = "", prompt_version: int = 1
    ) -> None:
        """Cache a message summary. Overwrites any prior one at this version."""
        self.conn.execute(
            "INSERT INTO summaries (message_id, summary, model, prompt_version, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(message_id) DO UPDATE SET "
            "summary=excluded.summary, model=excluded.model, "
            "prompt_version=excluded.prompt_version, created_at=excluded.created_at",
            (message_id, summary, model, prompt_version, datetime.now(UTC).isoformat()),
        )
        self.conn.commit()

    def summaries(self, prompt_version: int = 1) -> dict[str, str]:
        """message_id -> summary for every cached row at this prompt_version."""
        rows = self.conn.execute(
            "SELECT message_id, summary FROM summaries WHERE prompt_version=?",
            (prompt_version,),
        ).fetchall()
        return {r["message_id"]: r["summary"] for r in rows}

    # --- saved chats -------------------------------------------------------
    def create_chat(self, chat_id: str, title: str = "") -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT INTO chats (id, title, summary, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
            (chat_id, title, now, now),
        )
        self.conn.commit()

    def chat_exists(self, chat_id: str) -> bool:
        return (
            self.conn.execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone() is not None
        )

    def add_chat_message(
        self, chat_id: str, role: str, content: str, citations: list | None = None
    ) -> None:
        """Append a turn and bump the chat's updated_at.

        ``citations`` is stored as JSON as-is (ids or full citation objects), so a
        reloaded chat can render the same rich source cards it showed live.
        """
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT INTO chat_messages (chat_id, role, content, citations_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content, json.dumps(citations or []), now),
        )
        self.conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
        self.conn.commit()

    def chat_messages(self, chat_id: str) -> list[dict]:
        """A chat's turns, oldest first."""
        rows = self.conn.execute(
            "SELECT role, content, citations_json, created_at FROM chat_messages "
            "WHERE chat_id=? ORDER BY id",
            (chat_id,),
        ).fetchall()
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "citations": json.loads(r["citations_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def list_chats(self) -> list[dict]:
        """All chats, most recently updated first."""
        rows = self.conn.execute(
            "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows]

    def get_chat_summary(self, chat_id: str) -> str:
        row = self.conn.execute("SELECT summary FROM chats WHERE id=?", (chat_id,)).fetchone()
        return row["summary"] if row else ""

    def set_chat_summary(self, chat_id: str, summary: str) -> None:
        self.conn.execute("UPDATE chats SET summary=? WHERE id=?", (summary, chat_id))
        self.conn.commit()

    def set_chat_title(self, chat_id: str, title: str) -> None:
        self.conn.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id))
        self.conn.commit()

    # --- custom labels -----------------------------------------------------
    def create_label(self, label_id: str, name: str, color: str, instructions: str = "") -> None:
        self.conn.execute(
            "INSERT INTO labels (id, name, color, instructions, created_at) VALUES (?, ?, ?, ?, ?)",
            (label_id, name, color, instructions, datetime.now(UTC).isoformat()),
        )
        self.conn.commit()

    def list_labels(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, color, instructions FROM labels ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_label(self, label_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, color, instructions FROM labels WHERE id=?", (label_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_label(
        self,
        label_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        instructions: str | None = None,
    ) -> None:
        fields = {"name": name, "color": color, "instructions": instructions}
        changes = {k: v for k, v in fields.items() if v is not None}
        if not changes:
            return
        assigns = ", ".join(f"{k}=?" for k in changes)  # keys are fixed literals
        cur = self.conn.execute(
            f"UPDATE labels SET {assigns} WHERE id=?", [*changes.values(), label_id]
        )
        self.conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"unknown label_id: {label_id}")

    def delete_label(self, label_id: str) -> None:
        self.conn.execute("DELETE FROM email_labels WHERE label_id=?", (label_id,))
        self.conn.execute("DELETE FROM labels WHERE id=?", (label_id,))
        self.conn.commit()

    def set_email_label(self, message_id: str, label_id: str, on: bool) -> None:
        if on:
            self.conn.execute(
                "INSERT OR IGNORE INTO email_labels (message_id, label_id) VALUES (?, ?)",
                (message_id, label_id),
            )
        else:
            self.conn.execute(
                "DELETE FROM email_labels WHERE message_id=? AND label_id=?",
                (message_id, label_id),
            )
        self.conn.commit()

    def labels_for(self, message_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT label_id FROM email_labels WHERE message_id=?", (message_id,)
        ).fetchall()
        return [r["label_id"] for r in rows]

    def email_labels_map(self) -> dict[str, list[str]]:
        """message_id -> [label_id, ...] for every labelled email."""
        rows = self.conn.execute("SELECT message_id, label_id FROM email_labels").fetchall()
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["message_id"], []).append(r["label_id"])
        return out

    def label_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT label_id, COUNT(*) AS n FROM email_labels GROUP BY label_id"
        ).fetchall()
        return {r["label_id"]: r["n"] for r in rows}

    def close(self) -> None:
        self.conn.close()


def open_repository(db_path: str | Path) -> EmailRepository:
    """Open (or create) a repository. ``:memory:`` is passed through for tests."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return EmailRepository(conn)
