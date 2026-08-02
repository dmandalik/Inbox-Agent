# AGENTS.md — architecture & working notes

Orientation for any future session (human or agent). If you read only one file
before working here, read this one.

## What this is

An inbox AI agent, built in phases (see `README.md` "Status"). **Milestone 1
is complete**: a synthetic-data vertical slice — generate → ingest → triage →
eval — that runs keyless and offline. Later phases add RAG, agentic actions
with injection defense, observability, and a depth arc; interfaces are kept
clean so those slot in without rewrites.

Current state: 188 tests green, `ruff` clean, full-history `gitleaks` clean.
Triage stub scores accuracy 0.97 / macro-F1 0.97 on the 40-email golden set
(see the caveat in `README.md` — the stub is a floor, not a real result).
BM25 retrieval scores recall@5 1.00 / MRR 0.94 on 8 golden queries. Read-only
Gmail ingestion works on a live inbox.

## Design principles

- **Untrusted content.** Email bodies are attacker-controlled data, never
  instructions. The LLM classifier wraps bodies in delimiters and instructs the
  model to treat them as data. This discipline is the seed of Phase 3 security.
- **Everything behind an interface.** `EmailSource`, `LLMClient`, `Classifier`,
  (later) `Embedder`. Swapping providers/models/backends is config, not code.
- **Fail loudly.** Missing required config raises a clear, actionable error;
  we never fall back to a hardcoded secret or emit garbage labels silently.
- **Keyless by default in CI.** The `stub` triage backend needs no key and no
  network, so the full pipeline (and its integration test) runs anywhere.
- **Never log email content.** Bodies and addresses are simply never passed to a
  logger, which is stronger than redacting them. `obs.redact_secret` masks the
  one thing that does get logged: whether a credential is set.
- **One flat module per concept.** No package directory exists until there is
  more than one implementation worth separating. Prefer a 200-line file you can
  read in one sitting over five 40-line files and an `__init__.py`.

## Architecture

```
src/inbox_agent/
  models.py        The Email dataclass. Join key: message_id.
  synthetic.py     The fake corpus as a data table (no RNG) + read/write JSONL.
  store.py         SQLite schema + idempotent repository.
  email_source.py  EmailSource; Synthetic (default) + read-only Gmail.
  llm.py           LLMClient + OpenAI-compatible impl + retry/backoff.
  triage.py        Classifier + StubClassifier (rules) + LLMClassifier (zero-shot).
  retrieval.py     Retriever + BM25 "ask my inbox" + recall@k/MRR eval.
  rag.py           Grounded answer generation over hits + is_local_llm guard.
  summarize.py     Immutable per-message summary cache (chat context, L1).
  tools.py         Structured no-LLM tools: parse_intent + count/select/actions.
  chat.py          Conversational agent: tools first, else tiered retrieve + LLM.
  drafting.py      Reply drafting (local LLM only; a draft, never sends).
  labeling.py      Auto-apply user labels by their instructions (local LLM only).
  sanitize.py      nh3 allowlist sanitizer for rendering real email HTML safely.
  gmail_write.py   Gmail writes: send a reply, clear UNREAD (read/write scope).
  security.py      Injection attack suite + detect_injection backstop.
  api.py           FastAPI backend for the web UI. Read-only mail; /api/chat is
                   local-LLM-only (fail closed). See docs/CHAT_DESIGN.md.
  evals.py         P/R/F1, confusion matrix, text + Markdown reports (stdlib).
  config.py        Env-driven settings; require_llm() validates on use.
  obs.py           Logging, secret redaction, traced() seam (Phase-4 hook).
  cli.py           typer app: generate-data, ingest, triage, eval, ask, scan, serve.
data/synthetic/    Committed fake corpus (the ONLY committed email data).
data/golden/       Committed labels for eval.
data/real/  var/   Git-ignored. Real mail, DB, tokens, logs — never committed.
web/               Next + React frontend (the console). Talks to api.py.
                   node_modules/ and .next/ are git-ignored.
```

Reading order: `models` → `synthetic` → `store` → `triage` → `evals`. `cli`
wires them together; `config`/`obs`/`llm` are supporting cast.

### Data contract

Emails join on `message_id`. Stored fields: `message_id`, `thread_id`, `date`
(ISO), `from_addr`, `from_name`, `to`, `cc`, `subject`, `body`, `labels`,
`category` (ground truth). Triage output is kept in *separate* columns —
`predicted_category`, `predicted_backend`, `predicted_at` — so a label and a
prediction can never be conflated. User state (starred / read / archived) is
kept in its own columns and preserved across re-ingestion; a lightweight
migration adds these columns to older databases on open.

Re-ingestion is idempotent: `add_many()` upserts on `message_id`, refreshing
the source columns while **preserving** prediction columns, so re-ingesting
mail never silently discards triage results.

## Key decisions (and why)

- **OpenAI-compatible LLM client, not a vendor SDK.** One interface driven by
  `LLM_BASE_URL/API_KEY/MODEL` runs unchanged against Groq, Gemini, OpenRouter,
  and local Ollama/LM Studio. Provider = a `.env` edit.
- **Two triage backends behind one interface.** `stub` (deterministic
  keyword/sender rules) guarantees a keyless, offline, reproducible path for CI
  and smoke tests; `llm` (zero-shot) is the real classifier and the default when
  a key is present. Future embeddings/fine-tuned classifiers add as new backends.
- **SQLite + a hand-rolled repository.** Zero-infra, file-based, easy to reset;
  the repository layer hides SQL so a different store could replace it.
- **Stdlib eval metrics (no scikit-learn).** P/R/F1 + confusion matrix are ~40
  lines; avoids a heavy dependency for a small, transparent computation.
- **Gmail deps are an optional extra (`[gmail]`).** Base install stays light and
  fully offline; the real-Gmail path is opt-in and read-only.
- **The synthetic corpus is a fixture, not a random sample.** There is no RNG
  and no `datetime.now()` — message `i` is sent 37 minutes after message `i-1`.
  So a regenerate is byte-identical, eval numbers are reproducible, and the
  committed corpus never churns the diff. A seed would have bought nothing.
- **Predictions carry their backend.** `predicted_backend` means `eval` reports
  which classifier produced the numbers instead of guessing.
- **Retrieval (Phase 2) starts with BM25, not embeddings.** `rank-bm25` is a
  ~50 KB pure-Python dep (pulls only numpy); dense `sentence-transformers` would
  add ~2 GB of PyTorch. BM25 ships a working, private, offline "ask my inbox"
  plus a real recall@k/MRR eval now; a dense/hybrid `Retriever` slots in behind
  the same interface later, gated behind an optional extra. Retrieval is
  LLM-free, so it is safe on a real inbox — only the *generation* slice (later)
  needs an LLM, and on real mail that must be local (Ollama).
- **Retrieval relevance is judged at the thread level.** `GOLDEN_QUERIES` maps a
  question to `thread_id`s, resolved to `message_id`s against the corpus at eval
  time. Thread ids are stable, so the golden set survives message renumbering.
- **Injection defense is architectural, and honest about it.** The real
  guarantee is output clamping: triage can only emit a valid category, so no
  email can make it produce attacker text (tested with an obedient model fed the
  payload). `detect_injection` is explicitly a backstop, not a gate — it has
  false negatives by design, and no security decision rests on it. The attack
  suite exists so tests can assert 0/6 attacks reach their goal label and report
  a concrete number. See `THREAT_MODEL.md`.
- **The frontend reuses the mockup's CSS, not Tailwind.** The design was already
  hand-authored as CSS (warm palette, mono metadata, avatars); porting it into
  `web/app/globals.css` verbatim keeps the exact look with no conversion churn.
  `web/` is a lean Next app (no Tailwind, no create-next-app boilerplate); it
  proxies `/api/*` to FastAPI via `next.config.mjs`, so the browser calls
  same-origin and there is no CORS dance in dev.
- **The web API is a thin, read-only, LLM-free layer.** `api.py` holds no logic
  of its own — it calls the same store/triage/retrieval/security functions the
  CLI does, so the two never drift. The request path never calls an LLM: it
  serves a **stored** prediction if one exists (so a local `triage --backend
  llm`/Ollama run shows up in the UI) and falls back to the stub otherwise, plus
  BM25 for ask. That is what keeps it safe to serve a real inbox to a local
  frontend. Answer generation is deliberately not exposed; that needs the LLM
  and its privacy guard. FastAPI/uvicorn live in the `[web]` extra so the base
  install stays light. `inbox-agent serve` runs it.
- **Answer generation fails closed on a cloud LLM.** RAG sends retrieved email
  text to the model, so `ask --answer` refuses a non-local `LLM_BASE_URL` unless
  `--allow-cloud` is passed (`rag.is_local_llm`). Real mail → local Ollama (which
  speaks the OpenAI protocol, so no new client code — just `.env`). Retrieved
  emails go to the model as delimited, untrusted data with a no-obey instruction,
  same injection posture as triage. Retrieval itself never calls an LLM, so
  `ask` without `--answer` is always private.
- **The read-only Gmail source is split for testability.** `_message_to_email`
  and its helpers are pure functions over a Gmail API payload (headers, MIME
  parts, base64url, RFC-2047 encoded words) and are unit-tested offline. The
  network-touching `fetch` takes an injectable `service_factory`, so a fake
  Gmail service exercises the list/get pagination loop with no OAuth and no
  network. The earlier version had none of this coverage and was deleted during
  the simplify pass; this is the deliberate re-add, tested this time.
- **Gmail is now read/write** (`gmail.modify` + `gmail.send`) so the app can send
  replies and sync read-state. Writes live only in `gmail_write.py` (send + clear
  UNREAD); the destructive full-mailbox scope is refused in `gmail_service`, there
  is no delete path, sending is user-confirmed in the UI, and read-state sync is
  best-effort. Set `GMAIL_SCOPES` to just the readonly scope to lock it back down.

## Gotchas (learned the hard way — don't re-discover these)

- **`cli.py` must NOT use `from __future__ import annotations`.** typer resolves
  annotations at runtime; with the future import they become strings and
  `get_type_hints` blew up (`NameError: Optional`). Every other module keeps the
  future import.
- **Use `Annotated[X, typer.Option(...)]`, never `x: X = typer.Option(...)`.**
  Ruff's `B008` (function call in default) fails the pre-commit hook otherwise.
- **Ruff will rewrite `Optional[X]` → `X | None` (UP045)** and then strip the
  now-unused import. Write the union form directly.
- **`detect-secrets` flags ordinary prose.** Its *Secret Keyword* plugin reads
  "&lt;keyword&gt;: &lt;token&gt;" as an assignment, so a sentence that puts a
  word like *secret* or *credential* immediately before a colon and a
  backticked tool name looks like `password: hunter2`. Reword the sentence
  (split the clause, drop the colon) rather than baselining a false positive.
- **Never paste a credential-shaped literal into the docs.** Writing AWS's
  canonical `AKIA…EXAMPLE` value into this very file blocked the docs commit.
  Describe such values; don't quote them. (The hooks were right.)
- **Tests must pass `_env_file=None` to `Settings(...)`** so a developer's local
  `.env` can't leak a real key into a test asserting the no-key failure path.
- **gitleaks and detect-secrets have different blind spots — keep both.**
  Verified on this repo: gitleaks catches a PEM private key and a realistic
  GitHub `ghp_…` token, but **allowlists AWS's own documentation key pair**
  (the `AKIA…EXAMPLE` access key and its matching secret). `detect-secrets`
  catches those. Neither alone is sufficient; the pair is why the planted-key
  test blocks. Do not drop one to quiet a false positive.

## How to run

```bash
uv sync --extra dev
uv run pre-commit install
# keyless:
TRIAGE_BACKEND=stub uv run inbox-agent generate-data && \
  uv run inbox-agent ingest && uv run inbox-agent triage && uv run inbox-agent eval
# with a free key: put it in .env, then run the same four commands.
```

## How to test

```bash
uv run pytest            # unit + integration; unit tests never hit the network
uv run ruff check . && uv run ruff format --check .
```

Tests cover: store round-trip + idempotency + prediction preservation, the
synthetic generator (determinism, fake domains, injection samples), the email
sources (incl. Gmail's read-only-scope guard, offline payload parsing, and a
fake-service fetch loop), both classifiers (LLM mocked — **no unit test touches
the network**), the retry helper, eval metrics, BM25 retrieval + recall@k/MRR,
RAG answer generation (LLM mocked) + the fail-closed cloud-LLM guard, and a
keyless full-flow integration test
(`generate → ingest → triage → eval` with `TRIAGE_BACKEND=stub`).

## Secret & data protection

Defense-in-depth (full details in `README.md`):

1. `.gitignore` — secrets, `data/real/`, `var/`, `*.db` never tracked.
2. Pre-commit hooks **block** commits with secrets (gitleaks + detect-secrets +
   detect-private-key + large-file cap + ruff).
3. CI runs gitleaks over full history + the test suite.
4. GitHub Secret scanning + Push protection (must be enabled in repo settings).

### Leak-response protocol

A committed-then-deleted secret is **still leaked** — history is forever and a
public repo makes it permanent. If a secret reaches any commit:

1. **Rotate/revoke it immediately.** A history rewrite does not un-leak it;
   assume it is compromised the moment it was pushed.
2. **Scrub history** with `git filter-repo` (preferred) or BFG, then
   force-push and have collaborators re-clone.
3. **Verify** with `gitleaks detect` over the full history (expect zero findings).
4. Prevention at commit time is always cheaper than cleanup — keep the hooks on.

## Extension points (later phases)

- `Embedder` interface + `data/`-backed vector index → Phase 2 RAG.
- Action tools behind a validated harness + draft-commit pattern → Phase 3.
- `traced()` → real spans; evals gated in CI → Phase 4.
- Search `TODO(phase-N)` markers in the code for concrete seams.
