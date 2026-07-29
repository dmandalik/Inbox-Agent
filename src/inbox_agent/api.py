"""FastAPI backend for the web UI.

A thin, read-only JSON layer over the same functions the CLI uses — no logic
lives here that is not already in the library. It reads the local SQLite DB and
serves the current features: triage categories, the email list and detail, ask
your inbox (retrieval), and the injection scan.

Privacy: everything here is local and LLM-free (stub triage + BM25 retrieval),
so serving a real inbox to a local frontend sends nothing to the network.
Answer generation, which would call an LLM, is deliberately not exposed yet.

Run it with ``inbox-agent serve`` (needs the web extra: ``uv sync --extra web``).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from inbox_agent import __version__
from inbox_agent.config import get_settings
from inbox_agent.models import Email
from inbox_agent.retrieval import build_retriever
from inbox_agent.security import detect_injection
from inbox_agent.store import open_repository
from inbox_agent.triage import CATEGORIES, StubClassifier

app = FastAPI(title="Inbox Agent API", version=__version__)

# The Next dev server runs on :3000; allow it to call this API in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Stub triage is deterministic, keyless, and offline — the right default for a
# UI that must work on a real inbox without sending anything anywhere.
_classifier = StubClassifier()


def _load() -> tuple[list[Email], dict[str, str]]:
    """Return all emails plus the stored predictions map (message_id -> category)."""
    repo = open_repository(get_settings().db_path)
    try:
        return repo.all(), repo.predictions()
    finally:
        repo.close()


def _snippet(body: str, n: int = 140) -> str:
    return " ".join(body.split())[:n]


def _category(email: Email, preds: dict[str, str]) -> str:
    """Prefer a stored prediction (e.g. from `triage --backend llm`); else stub.

    This is why running `inbox-agent triage` with any backend shows up in the UI
    without the request path ever calling an LLM.
    """
    return preds.get(email.message_id) or _classifier.classify(email)


def _summary(email: Email, preds: dict[str, str]) -> dict:
    """List-row shape: enough to render a row, no full body."""
    return {
        "id": email.message_id,
        "thread_id": email.thread_id,
        "from_name": email.from_name,
        "from_addr": email.from_addr,
        "date": email.date,
        "subject": email.subject,
        "snippet": _snippet(email.body),
        "category": _category(email, preds),
        "flagged": detect_injection(f"{email.subject}\n{email.body}"),
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "categories": list(CATEGORIES)}


@app.get("/api/categories")
def categories() -> dict:
    emails, preds = _load()
    counts = dict.fromkeys(CATEGORIES, 0)
    flagged = 0
    for email in emails:
        counts[_category(email, preds)] = counts.get(_category(email, preds), 0) + 1
        if detect_injection(f"{email.subject}\n{email.body}"):
            flagged += 1
    return {
        "total": len(emails),
        "flagged": flagged,
        "categories": [{"id": c, "count": counts.get(c, 0)} for c in CATEGORIES],
    }


@app.get("/api/emails")
def list_emails(category: str | None = None, limit: int | None = None) -> dict:
    """List email summaries, optionally filtered by category or 'flagged'."""
    emails, preds = _load()
    summaries = [_summary(e, preds) for e in emails]
    if category == "flagged":
        summaries = [s for s in summaries if s["flagged"]]
    elif category and category != "all":
        summaries = [s for s in summaries if s["category"] == category]
    if limit is not None:
        summaries = summaries[:limit]
    return {"emails": summaries, "count": len(summaries)}


@app.get("/api/emails/{message_id}")
def get_email(message_id: str) -> dict:
    from fastapi import HTTPException

    repo = open_repository(get_settings().db_path)
    email = repo.get(message_id)
    prediction = repo.get_prediction(message_id)
    repo.close()
    if email is None:
        raise HTTPException(status_code=404, detail=f"no email with id {message_id}")
    preds = {message_id: prediction} if prediction else {}
    return {
        **_summary(email, preds),
        "to": email.to,
        "cc": email.cc,
        "labels": email.labels,
        "body": email.body,
    }


class AskRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """Retrieval only: the emails most relevant to a question. No LLM, private."""
    emails, _ = _load()
    retriever = build_retriever("bm25")
    retriever.index(emails)
    hits = [h for h in retriever.search(req.question, k=req.k) if h.score > 0]
    return {
        "question": req.question,
        "hits": [
            {
                "id": h.email.message_id,
                "from_name": h.email.from_name,
                "date": h.email.date,
                "subject": h.email.subject,
                "snippet": _snippet(h.email.body),
                "score": round(h.score, 2),
            }
            for h in hits
        ],
    }


@app.get("/api/scan")
def scan() -> dict:
    """Emails that look like prompt-injection attempts (heuristic backstop)."""
    emails, preds = _load()
    flagged = [s for s in (_summary(e, preds) for e in emails) if s["flagged"]]
    return {"flagged": flagged, "count": len(flagged)}
