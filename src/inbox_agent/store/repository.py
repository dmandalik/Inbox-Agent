"""Repository API over the SQLite ``emails`` table.

Hides SQL from the rest of the app and guarantees idempotent ingestion: adding
the same ``message_id`` twice never creates a duplicate, and re-ingesting
refreshes the source fields while **preserving** any existing triage prediction.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from inbox_agent.models import Email
from inbox_agent.store.db import connect, init_schema

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


def _email_to_row(e: Email) -> dict:
    return {
        "message_id": e.message_id,
        "thread_id": e.thread_id,
        "date": e.date,
        "from_addr": e.from_addr,
        "from_name": e.from_name,
        "to_json": json.dumps(e.to),
        "cc_json": json.dumps(e.cc),
        "subject": e.subject,
        "body": e.body,
        "labels_json": json.dumps(e.labels),
        "category": e.category,
    }


def _row_to_email(row: sqlite3.Row) -> Email:
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
    """CRUD + query surface for stored emails. Wraps one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        init_schema(self.conn)

    # --- ingestion ---------------------------------------------------------
    def add(self, email: Email) -> None:
        """Insert or refresh one email (idempotent; preserves predictions)."""
        self.add_many([email])

    def add_many(self, emails: list[Email]) -> int:
        """Upsert many emails. Returns the number processed.

        On conflict we UPDATE the source columns only — ``predicted_category``
        and ``predicted_at`` are deliberately left untouched so re-ingestion
        never silently discards triage results.
        """
        cols = ", ".join(_SOURCE_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in _SOURCE_COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _SOURCE_COLUMNS if c != "message_id")
        sql = (
            f"INSERT INTO emails ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(message_id) DO UPDATE SET {updates}"
        )
        rows = [_email_to_row(e) for e in emails]
        self.conn.executemany(sql, rows)
        self.conn.commit()
        return len(rows)

    # --- queries -----------------------------------------------------------
    def get(self, message_id: str) -> Email | None:
        cur = self.conn.execute("SELECT * FROM emails WHERE message_id = ?", (message_id,))
        row = cur.fetchone()
        return _row_to_email(row) if row else None

    def all(self) -> list[Email]:
        """All emails, ordered by date descending (newest first)."""
        cur = self.conn.execute("SELECT * FROM emails ORDER BY date DESC, message_id")
        return [_row_to_email(r) for r in cur.fetchall()]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0])

    def by_thread(self, thread_id: str) -> list[Email]:
        cur = self.conn.execute(
            "SELECT * FROM emails WHERE thread_id = ? ORDER BY date", (thread_id,)
        )
        return [_row_to_email(r) for r in cur.fetchall()]

    # --- predictions -------------------------------------------------------
    def set_prediction(self, message_id: str, category: str, when: str | None = None) -> None:
        ts = when or datetime.now(UTC).isoformat()
        cur = self.conn.execute(
            "UPDATE emails SET predicted_category = ?, predicted_at = ? WHERE message_id = ?",
            (category, ts, message_id),
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
        """message_id -> predicted_category, for rows that have a prediction."""
        cur = self.conn.execute(
            "SELECT message_id, predicted_category FROM emails WHERE predicted_category IS NOT NULL"
        )
        return {r["message_id"]: r["predicted_category"] for r in cur.fetchall()}

    def ground_truth(self) -> dict[str, str]:
        """message_id -> ground-truth category, for rows that have a label."""
        cur = self.conn.execute(
            "SELECT message_id, category FROM emails WHERE category IS NOT NULL"
        )
        return {r["message_id"]: r["category"] for r in cur.fetchall()}

    def close(self) -> None:
        self.conn.close()


def open_repository(db_path: str | Path) -> EmailRepository:
    """Open (or create) a repository at ``db_path``."""
    return EmailRepository(connect(db_path))
