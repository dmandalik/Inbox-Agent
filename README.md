# Inbox AI Agent

An AI agent that monitors an email inbox — it **triages** and flags messages,
answers **questions** about your mail (RAG, later phase), and **drafts replies**,
with strict human-in-the-loop control over anything that changes state.

This repository is a portfolio project built in phases. **Milestone 1 (this
release)** delivers an end-to-end, tested vertical slice that runs entirely on
**synthetic data**: generate a fake corpus → ingest into SQLite → triage with a
zero-shot LLM (or a keyless rule-based stub) → score with an eval harness.

> **Public-repo safety:** nothing sensitive is ever committable. Real email and
> the database live only in git-ignored paths; secrets are read from the
> environment; pre-commit + CI secret scanning block leaks at commit time. See
> [Secret & data protection](#secret--data-protection).

## Status

| Phase | What | State |
|------:|------|-------|
| 0 | Setup & ingestion (synthetic + Gmail-stub, SQLite) | ✅ Milestone 1 |
| 1 | Triage + eval harness | ✅ Milestone 1 |
| 2 | RAG Q&A (hybrid search + rerank) | ⬜ planned |
| 3 | Agentic actions + injection security | ⬜ planned |
| 4 | Observability, cost, CI-gated evals | ⬜ planned |
| 5 | Depth arc (MCP server *or* feedback-loop ML) | ⬜ planned |

## Quickstart (from a clean clone)

Prereqs: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), and (optionally) a
**free** LLM key. No paid service and no Gmail account are ever required.

```bash
# 1. Install (creates .venv, resolves deps)
uv sync --extra dev

# 2. Turn on the secret-scanning git hooks (do this before your first commit)
uv run pre-commit install

# 3a. KEYLESS run — deterministic stub classifier, no key, no network:
export TRIAGE_BACKEND=stub
uv run inbox-agent generate-data
uv run inbox-agent ingest
uv run inbox-agent triage
uv run inbox-agent eval

# 3b. REAL zero-shot LLM run — get a free key first, then:
cp .env.example .env          # edit .env: set LLM_API_KEY (Groq/Gemini free tier)
# (.env sets TRIAGE_BACKEND=llm by default)
uv run inbox-agent generate-data
uv run inbox-agent ingest
uv run inbox-agent triage
uv run inbox-agent eval
```

A **free LLM key** (no card) is all the `llm` backend needs:

- **Groq** — <https://console.groq.com> — default in `.env.example`.
- **Google AI Studio (Gemini)** — <https://aistudio.google.com/apikey>.
- **Local Ollama / LM Studio** — fully offline, no key. See `.env.example` presets.

Switching providers is a `.env` edit, never a code change (the client speaks the
OpenAI-compatible protocol).

## Triage categories

Every email is classified into one of six categories:

`newsletter` · `work` · `receipt_order` · `personal` · `spam_phishing` · `notification`

## Results

Zero-shot vs. keyless stub on the synthetic golden set. _(Numbers filled in
from `inbox-agent eval`; the stub is deterministic, the LLM row depends on the
model you point at.)_

<!-- RESULTS:START -->
_Run `inbox-agent eval` to populate this table._
<!-- RESULTS:END -->

## Configuration

All config is environment-driven (via a git-ignored `.env`); see `.env.example`
for every key and provider preset. Highlights:

| Var | Purpose | Default |
|-----|---------|---------|
| `TRIAGE_BACKEND` | `llm` (zero-shot) or `stub` (keyless rules) | `llm` |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | OpenAI-compatible endpoint | Groq preset |
| `DB_PATH` | SQLite location (under git-ignored `var/`) | `var/inbox.db` |
| `GMAIL_*` | Optional read-only Gmail path (never required) | `var/…` |

If `TRIAGE_BACKEND=llm` and no key is set, the tool **fails loudly** with an
actionable message instead of emitting garbage labels.

### Privacy rule (real inbox)

Milestone 1 is synthetic-only, so any free provider is fine. **The moment a real
inbox is connected**, switch the default to a **local model (Ollama)** or a
documented **no-training** provider — real email must never be sent to a free
tier that trains on prompts.

## Gmail (optional, read-only)

The default `EmailSource` is synthetic. A real Gmail read-only path is an
opt-in stub (`inbox_agent/email_source/gmail.py`). To enable it later:

```bash
uv sync --extra gmail
```

Then create a Google Cloud project, enable the Gmail API, download the OAuth
client secret to `var/credentials.json` (git-ignored), and use
`gmail.readonly` scope. No send/delete/modify scopes are used. Full steps are in
the stub's docstring. **You provide and manage these credentials yourself.**

## Development

```bash
uv run pytest            # tests (unit tests never touch the network)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pre-commit run --all-files
```

Architecture and design decisions live in [`AGENTS.md`](AGENTS.md).

## Secret & data protection

This is a **public** repo, so leak prevention is defense-in-depth:

1. **`.gitignore`** keeps secrets, real mail (`data/real/`), and the database
   (`var/`, `*.db`) out of the tree. Only `data/synthetic/` and `data/golden/`
   (obviously-fake content) are committed.
2. **Pre-commit hooks block a commit** the moment it contains a leaked
   credential. The hooks are `gitleaks`, `detect-secrets` (with
   `.secrets.baseline`), `detect-private-key`, and a `check-added-large-files`
   cap. Activate them:
   ```bash
   uv run pre-commit install
   ```
   Hooks can be bypassed with `--no-verify`, which is why CI and GitHub-side
   protection exist as backstops.
3. **CI secret-scan gate** (`.github/workflows/ci.yml`) runs `gitleaks` over the
   **full history** plus the test suite on every push/PR. Make it a required
   status check.
4. **GitHub-side protection — you must enable this** (Settings → Code security &
   analysis): turn on **Secret scanning** and **Push protection** so GitHub
   itself rejects pushes containing recognized secrets. Keep the repo **private
   until these protections are verified**, then flip to public.

If a secret ever lands in a commit, follow the **leak-response protocol** in
[`AGENTS.md`](AGENTS.md): rotate/revoke the key immediately, then scrub history.

## License

MIT — see `pyproject.toml`.
