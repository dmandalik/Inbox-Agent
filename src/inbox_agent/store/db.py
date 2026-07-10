"""SQLite connection + schema management.

One table, ``emails``, keyed by ``message_id``. Source columns hold the email
as ingested; ``predicted_category``/``predicted_at`` hold triage output and are
kept separate from the ground-truth ``category`` so we never conflate a label
with a prediction.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
    category           TEXT,            -- ground-truth label (synthetic only)
    predicted_category TEXT,            -- triage output (set by `triage`)
    predicted_backend  TEXT,            -- which classifier produced it (stub/llm)
    predicted_at       TEXT             -- ISO timestamp of the prediction
);
CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection, creating the parent dir if needed.

    ``:memory:`` is passed through unchanged (used by tests).
    """
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indexes if they don't exist (idempotent)."""
    conn.executescript(SCHEMA)
    conn.commit()
