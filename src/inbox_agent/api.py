"""FastAPI backend for the web UI.

A thin JSON layer over the same functions the CLI uses — no logic lives here
that is not already in the library. It serves triage categories, the email list
and detail (with filter/sort/search), ask your inbox (retrieval), the injection
scan, and per-email state (star / read / archive) via a PATCH endpoint.

"Read-only" applies to the *mail*: nothing here modifies email content or
touches the Gmail account. The only writes are local app state (flags) in our
own SQLite DB.

Privacy: the list/triage/retrieval paths are LLM-free (stub triage + BM25), so
serving a real inbox sends nothing to the network. The one path that does call
an LLM — ``/api/chat`` (answer generation + summaries) — is fail-closed to a
*local* model: a cloud endpoint is refused so a real inbox never leaves the box.

Run it with ``inbox-agent serve`` (needs the web extra: ``uv sync --extra web``).
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from inbox_agent import __version__
from inbox_agent.chat import ChatEngine, ChatTurn
from inbox_agent.config import ConfigError, get_settings
from inbox_agent.llm import build_llm_client
from inbox_agent.models import Email
from inbox_agent.rag import is_local_llm
from inbox_agent.retrieval import build_retriever
from inbox_agent.security import detect_injection
from inbox_agent.store import open_repository
from inbox_agent.summarize import Summarizer
from inbox_agent.triage import CATEGORIES, StubClassifier

app = FastAPI(title="Inbox Agent API", version=__version__)

# The Next dev server runs on :3000; allow it to call this API in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

# Stub triage is deterministic, keyless, and offline — the right default for a
# UI that must work on a real inbox without sending anything anywhere.
_classifier = StubClassifier()


_EMPTY_STATE = {"starred": False, "read": False, "archived": False}


def _load() -> tuple[list[Email], dict[str, str], dict[str, dict]]:
    """Return all emails, the stored predictions map, and the state map."""
    repo = open_repository(get_settings().db_path)
    try:
        return repo.all(), repo.predictions(), repo.states()
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


def _summary(email: Email, preds: dict[str, str], states: dict[str, dict]) -> dict:
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
        **states.get(email.message_id, _EMPTY_STATE),
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "categories": list(CATEGORIES)}


@app.get("/api/categories")
def categories() -> dict:
    """Category counts over the inbox (archived mail excluded, like the list)."""
    emails, preds, states = _load()
    counts = dict.fromkeys(CATEGORIES, 0)
    flagged = 0
    for email in emails:
        if states.get(email.message_id, _EMPTY_STATE)["archived"]:
            continue
        counts[_category(email, preds)] = counts.get(_category(email, preds), 0) + 1
        if detect_injection(f"{email.subject}\n{email.body}"):
            flagged += 1
    return {
        "total": sum(counts.values()),
        "flagged": flagged,
        "categories": [{"id": c, "count": counts.get(c, 0)} for c in CATEGORIES],
    }


_SORT_KEYS = {
    "date": lambda r: r["date"],
    "sender": lambda r: r["from_name"].lower(),
    "subject": lambda r: r["subject"].lower(),
    "category": lambda r: r["category"],
}


@app.get("/api/emails")
def list_emails(
    category: str | None = None,
    sender: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
    unread: bool | None = None,
    archived: bool = False,
    sort: str = "date",
    order: str = "desc",
    limit: int | None = None,
) -> dict:
    """List emails with filtering, sorting, and keyword search.

    Filtering happens in Python so the category logic stays single-sourced
    (predicted-or-stub); at inbox scale this is instant. Archived mail is hidden
    unless ``archived=true``.
    """
    emails, preds, states = _load()
    body_by_id = {e.message_id: e.body for e in emails}
    rows = [_summary(e, preds, states) for e in emails]

    rows = [r for r in rows if r["archived"] == archived]
    if category == "flagged":
        rows = [r for r in rows if r["flagged"]]
    elif category and category != "all":
        rows = [r for r in rows if r["category"] == category]
    if sender:
        needle = sender.lower()
        rows = [r for r in rows if needle in f"{r['from_name']} {r['from_addr']}".lower()]
    if q:
        needle = q.lower()
        rows = [
            r
            for r in rows
            if needle in f"{r['subject']} {r['from_name']} {body_by_id.get(r['id'], '')}".lower()
        ]
    if starred:
        rows = [r for r in rows if r["starred"]]
    if unread:
        rows = [r for r in rows if not r["read"]]

    rows.sort(key=_SORT_KEYS.get(sort, _SORT_KEYS["date"]), reverse=(order == "desc"))
    if limit is not None:
        rows = rows[:limit]
    return {"emails": rows, "count": len(rows)}


@app.get("/api/emails/{message_id}")
def get_email(message_id: str) -> dict:
    repo = open_repository(get_settings().db_path)
    email = repo.get(message_id)
    prediction = repo.get_prediction(message_id)
    state = repo.get_state(message_id) or _EMPTY_STATE
    repo.close()
    if email is None:
        raise HTTPException(status_code=404, detail=f"no email with id {message_id}")
    preds = {message_id: prediction} if prediction else {}
    return {
        **_summary(email, preds, {message_id: state}),
        "to": email.to,
        "cc": email.cc,
        "labels": email.labels,
        "body": email.body,
    }


class StatePatch(BaseModel):
    starred: bool | None = None
    read: bool | None = None
    archived: bool | None = None


@app.patch("/api/emails/{message_id}/state")
def set_state(message_id: str, patch: StatePatch) -> dict:
    """Flag/unflag, mark read/unread, or archive a single email."""
    repo = open_repository(get_settings().db_path)
    try:
        repo.set_state(message_id, starred=patch.starred, read=patch.read, archived=patch.archived)
        state = repo.get_state(message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        repo.close()
    return {"id": message_id, **(state or _EMPTY_STATE)}


class DraftRequest(BaseModel):
    guidance: str | None = None


@app.post("/api/emails/{message_id}/draft")
def draft(message_id: str, req: DraftRequest) -> dict:
    """Generate a reply draft for one email (local LLM only; never sends)."""
    client = _chat_client()  # may 400 on a cloud LLM
    if client is None:
        raise HTTPException(
            status_code=400,
            detail="Drafting needs a local LLM (e.g. Ollama). Set LLM_BASE_URL in .env.",
        )
    repo = open_repository(get_settings().db_path)
    try:
        email = repo.get(message_id)
    finally:
        repo.close()
    if email is None:
        raise HTTPException(status_code=404, detail=f"no email with id {message_id}")
    from inbox_agent.drafting import draft_reply

    return {"id": message_id, "draft": draft_reply(email, client, req.guidance)}


class AskRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """Retrieval only: the emails most relevant to a question. No LLM, private."""
    emails, _, _ = _load()
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
    emails, preds, states = _load()
    flagged = [s for s in (_summary(e, preds, states) for e in emails) if s["flagged"]]
    return {"flagged": flagged, "count": len(flagged)}


# --- conversational chat over the inbox -----------------------------------
def _chat_client():
    """A local LLM client for chat, or None if none is configured.

    Privacy guard: a real inbox must never be summarized or answered by a cloud
    model, so a configured-but-non-local LLM is refused outright. With no LLM at
    all, chat still works in a retrieval-only fallback (see :class:`ChatEngine`).
    """
    settings = get_settings()
    try:
        llm = settings.require_llm()
    except ConfigError:
        return None
    if not is_local_llm(llm.base_url):
        raise HTTPException(
            status_code=400,
            detail=(
                "Chat requires a LOCAL LLM (e.g. Ollama). Refusing to send your "
                "inbox to a cloud model. Set LLM_BASE_URL to a local endpoint."
            ),
        )
    return build_llm_client(settings)


class ChatRequest(BaseModel):
    message: str
    chat_id: str | None = None
    k: int = 5


def _citation_dict(c) -> dict:
    return {
        "id": c.message_id,
        "from_name": c.from_name,
        "subject": c.subject,
        "date": c.date,
        "summary": c.summary,
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """One conversational turn: retrieve, answer with citations, persist."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    client = _chat_client()  # may 400 on a cloud LLM, before any state changes
    repo = open_repository(get_settings().db_path)
    try:
        chat_id = req.chat_id
        if chat_id and not repo.chat_exists(chat_id):
            raise HTTPException(status_code=404, detail=f"no chat with id {chat_id}")
        if not chat_id:
            chat_id = uuid.uuid4().hex[:12]
            repo.create_chat(chat_id, title=message[:60])
        history = [ChatTurn(m["role"], m["content"]) for m in repo.chat_messages(chat_id)]
        engine = ChatEngine(repo.all(), Summarizer(repo, client), client, repo=repo)
        reply = engine.answer(message, history, k=req.k)
        repo.add_chat_message(chat_id, "user", message)
        repo.add_chat_message(
            chat_id, "assistant", reply.text, citations=[_citation_dict(c) for c in reply.citations]
        )
        return {
            "chat_id": chat_id,
            "reply": reply.text,
            "widened": reply.widened,
            "kind": reply.kind,
            "citations": [_citation_dict(c) for c in reply.citations],
        }
    finally:
        repo.close()


@app.get("/api/chats")
def chats() -> dict:
    """All saved conversations, most recently updated first."""
    repo = open_repository(get_settings().db_path)
    try:
        return {"chats": repo.list_chats()}
    finally:
        repo.close()


@app.get("/api/chats/{chat_id}")
def chat_history(chat_id: str) -> dict:
    """A saved conversation's turns (with per-turn citation ids)."""
    repo = open_repository(get_settings().db_path)
    try:
        if not repo.chat_exists(chat_id):
            raise HTTPException(status_code=404, detail=f"no chat with id {chat_id}")
        return {"chat_id": chat_id, "messages": repo.chat_messages(chat_id)}
    finally:
        repo.close()
