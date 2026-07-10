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
    predicted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);
"""

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

    def close(self) -> None:
        self.conn.close()


def open_repository(db_path: str | Path) -> EmailRepository:
    """Open (or create) a repository. ``:memory:`` is passed through for tests."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return EmailRepository(conn)
