# Conversational inbox agent — design

Goal: chat with an AI about your inbox ("summarize the thread with my landlord",
"what's the deadline in the Stripe email", "did anyone email me about the
flight?"). It must be **accurate** (grounded in real emails, cites them, never
invents) and **cheap** — designed so that, at millions of users, it burns the
fewest tokens possible.

## North star: the cheapest token is the one you never send

Every design choice below exists to avoid sending text to the LLM. The layers
answer in order; each more expensive layer only runs when the cheaper one can't.

| Layer | What it does | Saves |
|------|--------------|-------|
| **L0 — no LLM** | Structured questions ("how many unread", "from X last week") answered by SQL/filters, not the model | 100% of tokens for those queries |
| **L1 — immutable summary cache** | Feed short cached per-email / per-thread summaries into context, not raw bodies | ~5–10× context reduction |
| **L2 — tiered retrieval** | Search a recent window first; widen to full history only on a weak hit | Most queries never touch old mail |
| **L3 — retrieve wide, send narrow** | BM25 top-N locally (free), send only top-k (3–5) summaries to the model | Caps prompt size hard |
| **L4 — rolling chat compaction** | Keep last K turns verbatim + a running summary of older turns | Kills quadratic history growth |
| **L5 — skip needless calls** | No query-rewrite call on turn 1 (no history to fold in) | One call per new conversation |

### The property that makes all of this cheap: **email is immutable**

A received message's body never changes. So:

- **Per-message summary** — compute **once**, cache **forever**, keyed by
  `(message_id, prompt_version)`. It never invalidates. Bump `prompt_version`
  to re-summarize the whole corpus intentionally.
- **Per-thread summary** — invalidates only when a *new* message is appended to
  the thread; then we fold just the new message in (incremental, not a rebuild).
- **BM25 index** — append-only; can be persisted and grown instead of rebuilt.

This is why "saved context boxes per email/thread" (the idea in the prompt) is
the single biggest lever: you summarize an email one time in its life and reuse
that summary across every future chat, for every question, for that user.

## Answering the specific questions raised

1. **Recent-first, then index the rest on a miss?** Yes — that's **L2**. Note
   the real win: BM25 over even 100k emails is sub-millisecond, so this isn't
   about index *speed*. It's about **scope**: a recent window means fewer, more
   relevant candidates, which means fewer summaries in the prompt = fewer
   tokens, and a small model that isn't distracted by years of old mail.

2. **Saved context boxes per email/thread so we don't reprocess every time?**
   Yes — that's **L1**, and it's the highest-value idea here. Because email is
   immutable the cache is permanent and never goes stale. We summarize on
   ingest (amortized, off the hot path) or lazily on first touch, store it in
   SQLite, and every chat reads summaries instead of re-reading bodies.

3. **Saving chats?** Yes — **L4**. Persist conversations so a user can resume,
   *and* so we can compact them: re-sending a whole transcript every turn is
   quadratic. We keep the last few turns verbatim plus a rolling summary of the
   older ones, so per-turn cost stays flat no matter how long the chat gets.

## Two cost regimes (same architecture)

- **This local build (Ollama / llama3.2):** tokens are free. The wins here are
  **latency** and **fitting a small model's context window** — a 3B model gets
  *more accurate* when you feed it 4 tight summaries instead of 40 raw emails.
- **Cloud at scale:** the identical design is the difference between viable and
  bankrupt. We build it once, correctly, now.

## Request flow (one chat turn)

```
user message
  │
  ├─ L0 router: is this a structured/count question?  ── yes ─▶ answer from SQL, no LLM
  │                                                              (cite the rows)
  ├─ L5: turn 1?  ── no ─▶ rewrite into a standalone query using recent history
  │
  ├─ L2/L3: BM25 over the recent tier → top-N; if weak, widen to full corpus
  │         take top-k, load their CACHED summaries (L1; summarize+cache on miss)
  │
  ├─ compose grounded prompt: standalone question + numbered summary blocks
  │   (emails are UNTRUSTED DATA — never instructions; cite [n]; say "I don't
  │    have an email about that" when absent)
  │
  ├─ privacy guard: real inbox ⇒ local LLM only (fail closed), reuse is_local_llm
  │
  └─ LLM answer (stream) → persist turn → return {reply, citations:[message_id…]}
```

## Data model (additions)

```sql
-- immutable per-message summary cache (L1)
CREATE TABLE summaries (
    message_id     TEXT PRIMARY KEY,
    summary        TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    created_at     TEXT NOT NULL
);

-- incremental per-thread summary (L1)
CREATE TABLE thread_summaries (
    thread_id       TEXT PRIMARY KEY,
    summary         TEXT NOT NULL,
    last_message_id TEXT NOT NULL,   -- fold in anything newer than this
    model           TEXT NOT NULL,
    prompt_version  INTEGER NOT NULL,
    updated_at      TEXT NOT NULL
);

-- saved conversations (L4)
CREATE TABLE chats (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',  -- rolling summary of older turns
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE chat_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id        TEXT NOT NULL,
    role           TEXT NOT NULL,          -- 'user' | 'assistant'
    content        TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL
);
```

All additive and created with `IF NOT EXISTS`, matching the existing
migration-friendly store. Emails are immutable, so summaries never need cache
invalidation on content change — only on a deliberate `prompt_version` bump.

## Build order

1. **Summary cache** — `summarize.py` + `summaries` table + repo methods. Lazy,
   cached, versioned. *(this turn)*
2. **Chat engine** — `chat.py`: tiered retrieve → summary-grounded answer with
   citations, reusing the untrusted-data / citation discipline from `rag.py`.
   *(this turn)*
3. **Persistence + compaction** — `chats` / `chat_messages`, rolling summary.
4. **API** — `POST /api/chat`, `GET /api/chats`, `GET /api/chats/{id}` (JSON
   first for tests, streaming after).
5. **UI** — chat panel with streaming and clickable citation cards.
6. **L0 router + Track B tools** — structured questions answered without the LLM.

Every step keeps the privacy guard (real mail ⇒ local LLM only) and treats
email bodies as untrusted data.
