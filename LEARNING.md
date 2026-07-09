# LEARNING.md — Inbox AI Agent

A build-and-learn plan for an AI agent that monitors an inbox, answers questions
about it, and triages / flags / drafts on your behalf. The plan is ordered so that
**you learn each concept exactly when the build needs it**, and every phase ends
with a concrete artifact for your GitHub README and resume.

## Goals

- **Deep, granular AI/ML knowledge** — real techniques (retrieval, evals, fine-tuning, security), not just API calls.
- **Learn a lot** — touch most sub-fields of modern applied AI in one coherent project.
- **Ship something usable** — a real agent connected to a real inbox.
- **A strong GitHub repo** — measurable results, a clean README, and a design story.

## How to use this plan

- Work top to bottom. The order is deliberate: instrument and measure early, add write-access and autonomy late.
- Check boxes as you go: `[ ]` → `[x]`.
- Each phase has three parts: **Build** (what to ship), **Learn** (resources), **Milestone** (the artifact to show).
- Pick your **arc** (see below) once you reach Phase 5 — don't try to build everything.
- Keep the **Foundations track** running in the background whenever you want more depth.

## Guardrails (read once, apply always)

- [ ] Never commit real email. Use a throwaway test account or synthetic data. `.gitignore` credentials, tokens, and any mailbox export.
- [ ] Start every integration **read-only**; add write access only after Phase 3's security work.
- [ ] Treat all email content as **untrusted data, never instructions** (this is the whole point of Phase 3).

---

## The two arcs — pick one for Phase 5+

Both share Phases 0–4. Choose based on the internships you want.

- **Arc A — Production AI Engineering** (infra / agent-eng roles): MCP server + autonomy ladder + model-cascade router + a benchmark leaderboard. Story: *"I ship reliable, cost-aware agents."*
- **Arc B — Real ML** (ML / research-leaning roles): triage classifier → feedback loop → active learning → DPO from draft edits. Story: *"I understand the model, not just the API."*

- [ ] Decided which arc to pursue: ____________________

---

## Foundations track (parallel / background — optional but high-payoff)

Understand the model instead of treating it as magic. Do this alongside the phases.

- [ ] **Karpathy, "Neural Networks: Zero to Hero"** — build nets from scratch up to a GPT. https://karpathy.ai/zero-to-hero.html · code: https://github.com/karpathy/nn-zero-to-hero
- [ ] **Hugging Face LLM Course** — NLP foundations → modern LLMs, fine-tuning, deployment. https://huggingface.co/learn/llm-course/chapter1/1

---

## Phase 0 — Foundations & Setup

**Build**
- [ ] Read *Building Effective Agents* before writing any code (one afternoon).
- [ ] Create a throwaway Gmail test account; enable the Gmail API; complete the Python quickstart (`gmail.readonly` scope).
- [ ] Ingest messages into local storage with metadata (sender, date, thread ID, labels).
- [ ] Set up the repo: `.gitignore` for secrets, a README stub, and an `AGENTS.md`.

**Learn**
- [ ] Anthropic, **Building Effective Agents** — the mental model (workflows vs. agents; keep it simple). https://www.anthropic.com/research/building-effective-agents
- [ ] Anthropic cookbook — runnable agent patterns. https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents
- [ ] **Gmail API** Python quickstart. https://developers.google.com/workspace/gmail/api/quickstart/python
- [ ] Gmail API overview (messages, threads, drafts, labels, filters). https://developers.google.com/gmail/api/guides
- [ ] Optional friendlier wrapper: **simplegmail**. https://github.com/jeremyephron/simplegmail

**Milestone**
- [ ] A script that authenticates and pulls N emails into a local store with metadata.

---

## Phase 1 — Triage classifier + eval harness (build these together)

Build the eval scaffold *first* so you measure from day one. Triage (auto-categorize / flag)
is where you can show real ML on a ladder of increasing depth.

**Build**
- [ ] Golden dataset: a few hundred emails labeled with categories you care about.
- [ ] Eval harness: run predictions vs. labels, report accuracy / F1 per class.
- [ ] Classifier ladder (climb as far as you like):
  - [ ] Zero-shot LLM prompt
  - [ ] Few-shot with curated examples
  - [ ] Embeddings + a lightweight classifier (logistic regression / small MLP)
  - [ ] (Stretch, Arc B) LoRA fine-tune of a small encoder
- [ ] Handle class imbalance and threshold/calibration tuning; note cost & latency per approach.

**Learn**
- [ ] Hamel Husain, **"Your AI Product Needs Evals"** — why generic metrics fail; error analysis first. https://hamel.dev/blog/posts/evals/
- [ ] Hamel Husain, **"LLM-as-a-Judge"** — binary pass/fail judges, validated against human labels. https://hamel.dev/blog/posts/llm-judge/
- [ ] Hamel Husain, **"Evals FAQ"** — the sharp-edges reference. https://hamel.dev/blog/posts/evals-faq/
- [ ] Free **50-minute eval crash course** (spreadsheet workflow). https://creatoreconomy.so/p/ai-evaluations-crash-course-in-50-minutes-hamel-husain
- [ ] (Optional, paid) **AI Evals for Engineers & PMs** (Maven). https://maven.com/parlance-labs/evals

**Milestone**
- [ ] A README table: triage F1 by approach (e.g., zero-shot 0.74 → embeddings+classifier 0.91).

---

## Phase 2 — RAG Q&A over the inbox

Ask questions across your mail. Do retrieval *properly* and measure it.

**Build**
- [ ] Thread-aware, metadata-rich chunking.
- [ ] Dense embeddings + a vector store; add BM25 for hybrid search; fuse with RRF.
- [ ] Add a cross-encoder reranker over fused candidates.
- [ ] Retrieval evals: recall@k / MRR on a labeled query set.
- [ ] Generation evals with the RAG framework: context relevance, faithfulness, answer relevance.

**Learn**
- [ ] **Hybrid Search & Re-Ranking in Production RAG** — bi- vs. cross-encoders, "lost in the middle." https://towardsdatascience.com/hybrid-search-and-re-ranking-in-production-rag/
- [ ] **Implementing Hybrid Semantic-Lexical Search** — concrete BM25 + sentence-transformers code. https://machinelearningmastery.com/implementing-hybrid-semantic-lexical-search-in-rag/
- [ ] **Jason Liu, "There Are Only 6 RAG Evals"** — retrieval IR metrics + Question/Context/Answer relationships (linked from Hamel's Evals FAQ above).
- [ ] Hugging Face **Agents Course** — the Agentic RAG and tracing/evaluation units. https://huggingface.co/learn/agents-course/en/unit0/introduction

**Milestone**
- [ ] "Ask my inbox" Q&A with a README table of retrieval metrics + RAG-triad scores.

---

## Phase 3 — Agentic actions + security (the standout depth for an *email* agent)

Email is attacker-controlled input. This phase is what makes the project rare and impressive.

**Build**
- [ ] Tools for actions (label, archive, draft) behind a validated harness.
- [ ] **Draft-commit pattern**: the model proposes; a guard or human confirms every state-changing action.
- [ ] Permission tiers / least privilege for tools.
- [ ] Trust labeling: separate and mark untrusted email content so it can't act as instructions.
- [ ] An **injection attack suite** (emails that try to hijack the agent) + a test that they're all blocked.
- [ ] A one-page **threat model** in the repo.

**Learn**
- [ ] **OWASP Top 10 for LLM Applications (2025)** — prompt injection is #1; defense in depth. https://genai.owasp.org/llm-top-10/
- [ ] **OWASP Agentic AI Top 10 (2025)** — risks once the agent can act autonomously (same OWASP GenAI project site).
- [ ] **Simon Willison — Dual LLM pattern** and prompt-injection writing. https://simonwillison.net/ (see his prompt-injection tag)
- [ ] **DeepTeam** — run OWASP attack suites against your agent. https://www.trydeepteam.com/docs/frameworks-owasp-top-10-for-llms

**Milestone**
- [ ] Threat model doc + "blocked N/N injection attacks" result in the README.

---

## Phase 4 — Observability, cost, and CI-gated evals

Turn the demo into a system with the signals reviewers look for.

**Build**
- [ ] Trace every step (LLM calls, tool calls, retrieval); track cost + latency per query.
- [ ] Response caching (consider a semantic cache) with a reported hit rate.
- [ ] Run your Phase 1–2 evals in CI so a regression fails the build.
- [ ] Structured-output schema validation; prompt versioning.

**Learn**
- [ ] **Langfuse** docs — open-source, self-hostable tracing + evals. https://langfuse.com/docs
- [ ] **OpenTelemetry GenAI semantic conventions** — keep instrumentation vendor-neutral (opentelemetry.io).
- [ ] Re-read the eval cadence in Hamel's "Your AI Product Needs Evals" — cheap code evals every change, model-based on a cadence.

**Milestone**
- [ ] A dashboard/trace view + a CI badge showing evals gate merges; a cost-per-query number.

---

## Phase 5 — Choose your arc and go deep

### Arc A — Production AI Engineering
- [ ] **Expose the agent as an MCP server** (search, summarize, draft, label as tools/resources). Ship read-only first.
  - [ ] Official MCP "Build a server" quickstart. https://modelcontextprotocol.io/docs/develop/build-server
  - [ ] Python SDK / FastMCP + the MCP Inspector. https://github.com/modelcontextprotocol/python-sdk
  - [ ] Anthropic's MCP course. https://anthropic.skilljar.com/introduction-to-model-context-protocol
- [ ] **Autonomy ladder**: recommendation → supervised action → limited autonomy, as permission tiers.
- [ ] **Model-cascade router**: cheap/local model for easy queries, frontier for hard ones (report cost savings).
- [ ] **Benchmark leaderboard**: run multiple models against your golden set with one harness; publish the table.

### Arc B — Real ML
- [ ] **Closed feedback loop**: capture re-categorizations and draft edits as labeled data.
- [ ] **Active learning**: surface the most uncertain classifications for labeling; retrain periodically.
- [ ] **Style-matched drafting**: retrieve similar past sent replies as few-shot, then LoRA fine-tune on the sent folder.
- [ ] **DPO from draft edits**: treat (draft, edited) pairs as preference data; align a small model.
  - [ ] **Unsloth** fine-tuning guide (LoRA/QLoRA/DPO, single-GPU friendly). https://unsloth.ai/docs/get-started/fine-tuning-llms-guide
  - [ ] **Hugging Face TRL** — SFT / DPO / reward modeling (SFTTrainer, DPOTrainer).
  - [ ] End-to-end **fine-tune + deploy playbook**. https://www.decodingai.com/p/playbook-to-fine-tune-and-deploy

**Milestone**
- [ ] Arc A: a working MCP server others can connect + a cost-savings number from the router.
- [ ] Arc B: a resume line like "applied DPO to align draft generation, acceptance rate X→Y."

---

## Portfolio checklist (do these no matter which arc)

- [ ] README with an architecture diagram, an eval-results table, and a short demo GIF.
- [ ] A design doc or blog post explaining your retrieval and injection-defense decisions (this often gets the interview).
- [ ] Tests + CI (with eval gates).
- [ ] `AGENTS.md` for the repo.
- [ ] Clearly-labeled "Future work" section for the arc you didn't build.
- [ ] Synthetic-data generator (bootstraps evals/training *and* keeps the public repo private-data-free).

## Staying current

- [ ] Anthropic Engineering blog — agent patterns, context engineering, deployment.
- [ ] Simon Willison's blog — practical LLM + security notes.
- [ ] Hamel Husain's blog — evals and data flywheels.
- [ ] Model Context Protocol updates (modelcontextprotocol.io) and the OWASP GenAI project.

---

### Suggested first two weeks
1. Read *Building Effective Agents*; stand up the Gmail quickstart (read-only).
2. Start Hamel's free eval workflow and build the golden dataset in parallel.
3. Ship the zero-shot triage classifier measured by the eval harness — your first README number.
