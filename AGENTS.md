# AGENTS.md — architecture & working notes

Orientation for any future session (human or agent). If you read only one file
before working here, read this one.

## What this is

An inbox AI agent, built in phases (see `README.md` "Status"). **Milestone 1**
is a synthetic-data vertical slice: generate → ingest → triage → eval. Later
phases add RAG, agentic actions with injection defense, observability, and a
depth arc — interfaces are kept clean so those slot in without rewrites.

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
- **Redact by default.** Bodies, addresses, keys, and tokens go through
  `obs.redact` before they can reach a log or exception.

## Architecture

```
src/inbox_agent/
  config.py          Settings (pydantic-settings, env-driven). require_llm() validates on use.
  llm/               LLMClient interface + OpenAI-compatible impl (429 backoff).
  email_source/      EmailSource interface; SyntheticEmailSource (default) + Gmail stub (read-only).
  store/             SQLite schema + idempotent repository (join key: message_id).
  triage/            Classifier interface; StubClassifier (rules) + LLMClassifier (zero-shot).
  evals/             metrics (P/R/F1, confusion matrix, stdlib) + harness + report.
  synthetic/         Seeded fake-email generator (deterministic corpus).
  obs/               logging, redaction, traced() seam (Phase-4 tracing hook).
  cli.py             typer app: generate-data, ingest, triage, eval.
data/synthetic/      Committed fake corpus (the ONLY committed email data).
data/golden/         Committed labels for eval.
data/real/  var/     Git-ignored. Real mail, DB, tokens, logs — never committed.
```

### Data contract

Emails join on `message_id`. Stored fields: `message_id`, `thread_id`, `date`
(ISO), `from_addr`, `from_name`, `to`, `cc`, `subject`, `body`, `labels`,
`category` (ground truth). Re-ingestion is idempotent (upsert on `message_id`).

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
- **Deterministic, seeded synthetic generator.** The committed corpus is stable
  across runs so eval numbers and tests are reproducible.

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

Tests cover: store round-trip + idempotency, synthetic source, both classifiers
(LLM mocked), eval metrics, and a keyless full-flow integration test
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
