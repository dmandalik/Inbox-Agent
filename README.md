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
| 0 | Setup & ingestion (synthetic + read-only Gmail, SQLite) | ✅ Milestone 1 |
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

## How it works

```
generate-data          ingest              triage                eval
┌──────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│ synthetic    │──▶│ EmailSource  │──▶│  Classifier   │──▶│ metrics +    │
│ generator    │   │  → SQLite    │   │ stub  |  llm  │   │ confusion mx │
│ (seeded)     │   │ (idempotent) │   │ (zero-shot)   │   │  P/R/F1      │
└──────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
 data/synthetic/      var/inbox.db      TRIAGE_BACKEND       data/golden/
```

Each stage sits behind an interface (`EmailSource`, `LLMClient`, `Classifier`)
so later phases — RAG, agentic actions, a model-cascade router — slot in without
rewrites.

## Project layout

One flat module per concept — read them top to bottom, in this order:

| File | Lines | What it is |
|------|------:|------------|
| `models.py` | ~35 | The `Email` dataclass. Everything joins on `message_id`. |
| `synthetic.py` | ~230 | The fake corpus, as a plain data table. No RNG. |
| `store.py` | ~170 | SQLite schema + repository. Idempotent ingestion. |
| `email_source.py` | ~250 | `EmailSource`: synthetic (default) + read-only Gmail. |
| `llm.py` | ~110 | `LLMClient` + OpenAI-compatible impl + retry/backoff. |
| `triage.py` | ~230 | `Classifier` + the two backends, side by side. |
| `evals.py` | ~150 | Precision/recall/F1, confusion matrix, reports. |
| `config.py` | ~85 | Env-driven settings. Fails loudly when unconfigured. |
| `obs.py` | ~60 | Logging, secret redaction, `traced()` seam. |
| `cli.py` | ~165 | The four commands. |

```
data/synthetic/   Committed fake corpus — the ONLY committed email data.
data/golden/      Committed eval labels.
data/real/  var/  Git-ignored: real mail, DB, tokens, logs.
tests/            One test file per module.
```

**If you're reading this to learn it**, start at `models.py`, then follow the
pipeline: `synthetic.py` → `store.py` → `triage.py` → `evals.py`. `cli.py`
just wires those four together.

## Results

Scored on the synthetic golden set (40 emails, 6 classes) with
`inbox-agent eval`.

<!-- RESULTS:START -->
### `stub` backend (deterministic rules, keyless)

**Backend:** `stub` · **n:** 40 · **accuracy:** 0.97 · **macro-F1:** 0.97

| category | precision | recall | F1 | support |
|----------|----------:|-------:|---:|--------:|
| newsletter | 0.88 | 1.00 | 0.93 | 7 |
| work | 1.00 | 1.00 | 1.00 | 10 |
| receipt_order | 1.00 | 1.00 | 1.00 | 6 |
| personal | 1.00 | 1.00 | 1.00 | 5 |
| spam_phishing | 1.00 | 1.00 | 1.00 | 6 |
| notification | 1.00 | 0.83 | 0.91 | 6 |
| **macro avg** | 0.98 | 0.97 | 0.97 | 40 |

The single error is one `notification` predicted as `newsletter` (an automated
digest whose body mentions unsubscribing).

> **Read this number honestly.** The stub's rules were written against *this*
> taxonomy and *this* generator, so 0.97 measures rule-fitting, not
> generalization — it is a **floor and a regression guard**, not a result to
> brag about. The interesting comparison is the zero-shot LLM, which sees the
> categories only through a prompt and has never seen the corpus.

### `llm` backend (zero-shot)

Run it yourself with a free key — numbers depend on the model you point at:

```bash
cp .env.example .env      # set LLM_API_KEY
uv run inbox-agent triage --backend llm && uv run inbox-agent eval --markdown
```

<!-- Paste your zero-shot table here once you've run it against a provider. -->

_Not yet filled in: this requires an API key, which the author supplies — the
repo intentionally ships no credentials. Phase 1 of `LEARNING.md` adds
few-shot and embedding-based classifiers to this table._
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

The default `EmailSource` is synthetic. A real Gmail path is implemented in
`inbox_agent/email_source.py` (`GmailEmailSource`) and is **opt-in and
read-only** — it refuses any scope other than `gmail.readonly`, so it can never
send, delete, or modify mail.

**One-time setup (you own the credentials — never paste them anywhere but
git-ignored `var/`):**

1. In the [Google Cloud console](https://console.cloud.google.com), create a
   project and **enable the Gmail API** (APIs & Services → Library).
2. Configure the **OAuth consent screen** (External); add your address as a
   test user.
3. Create an **OAuth client ID → Desktop app**, download the JSON, and save it
   as `var/credentials.json`.
4. Install the optional deps and run:
   ```bash
   uv sync --extra gmail
   uv run inbox-agent ingest --source gmail --limit 20
   uv run inbox-agent triage --backend stub   # or llm, with a key
   ```

The first `ingest` opens a browser once for read-only consent; the token caches
to `var/token.json` (git-ignored) so later runs are non-interactive.

Use a **throwaway Gmail account** to demo this. Note there are **no
ground-truth labels** on a real inbox, so `triage` produces predictions but
`eval` has nothing to score — accuracy numbers only mean something on the
labeled synthetic set.

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

### Verify the protections yourself

```bash
# 1. No secret anywhere in the FULL history:
gitleaks detect                       # expect: "no leaks found"

# 2. All hooks pass on every file:
uv run pre-commit run --all-files

# 3. The hooks actually BLOCK a planted key (this commit must fail).
#    Put any credential-shaped string in the file — e.g. a fake PEM private key,
#    or AWS's canonical AKIA…EXAMPLE pair from their docs. (Don't commit this
#    README with a literal key in it: the hooks will — correctly — stop you.)
echo '<paste a fake credential here>' > leak_test.txt
git add leak_test.txt && git commit -m "should be blocked"   # <- expect BLOCKED
git restore --staged leak_test.txt && rm leak_test.txt

# 4. Nothing sensitive is tracked:
git ls-files | grep -E '(^\.env$|credentials|token|\.db$|^data/real/|^var/)'   # expect: no output
```

All four are part of this milestone's definition of done and pass on `main`.

> **Why two scanners?** They have different blind spots. Verified here:
> `gitleaks` catches a PEM private key and a realistic GitHub `ghp_…` token, but
> *allowlists* AWS's own documentation key pair (the `AKIA…EXAMPLE` value) —
> which `detect-secrets` catches. Running both is what makes step 3 fail.
> Neither is sufficient alone, and GitHub Push Protection backstops both.

## License

MIT — see [`LICENSE`](LICENSE).
