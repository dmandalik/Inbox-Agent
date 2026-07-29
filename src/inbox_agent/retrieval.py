"""Ask-my-inbox retrieval: find the emails relevant to a question.

Phase 2, slice 1 — retrieval only, fully local and private (no LLM, no
network), so it is safe to run over a real inbox. Answer *generation* is a
later slice that adds an LLM on top of these hits.

One :class:`Retriever` interface with a keyword :class:`BM25Retriever`. Dense
embeddings and hybrid fusion slot in later behind the same interface (mirroring
the Classifier / EmailSource pattern), so ``ask`` never changes.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from inbox_agent.models import Email

# A small, high-value stopword list — enough to stop "the/is/to" from dominating
# BM25 scores without pulling in a heavyweight NLP dependency.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "you",
        "your",
    ]
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def _document(email: Email) -> str:
    """The text we index for an email. Sender is included so 'emails from Priya'
    works; the subject is repeated once to give it a little more weight."""
    return f"{email.subject} {email.subject} {email.from_name} {email.from_addr} {email.body}"


@dataclass(frozen=True)
class Hit:
    """One retrieval result: an email and its relevance score."""

    email: Email
    score: float


class Retriever(ABC):
    """Indexes a set of emails and returns the most relevant for a query."""

    name: str = "retriever"

    @abstractmethod
    def index(self, emails: list[Email]) -> None:
        """(Re)build the index over ``emails``."""

    @abstractmethod
    def search(self, query: str, k: int = 5) -> list[Hit]:
        """Return up to ``k`` hits, most relevant first."""


class BM25Retriever(Retriever):
    """Okapi BM25 keyword retrieval. Deterministic, offline, no model download."""

    name = "bm25"

    def __init__(self) -> None:
        self._emails: list[Email] = []
        self._bm25: BM25Okapi | None = None

    def index(self, emails: list[Email]) -> None:
        self._emails = list(emails)
        corpus = [tokenize(_document(e)) for e in self._emails]
        # BM25Okapi requires a non-empty corpus; guard the empty-inbox case.
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, k: int = 5) -> list[Hit]:
        tokens = tokenize(query)
        if not self._bm25 or not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            zip(self._emails, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
        return [Hit(email, float(score)) for email, score in ranked[:k]]


def build_retriever(name: str = "bm25") -> Retriever:
    """Return a retriever by name. Only 'bm25' exists today."""
    if name == "bm25":
        return BM25Retriever()
    raise ValueError(f"unknown retriever: {name!r} (expected 'bm25')")


# --------------------------------------------------------------------------
# Retrieval eval — a golden query set over the synthetic corpus
# --------------------------------------------------------------------------

# Relevance is judged at the *thread* level (stable across corpus renumbering):
# each question maps to the thread_id(s) whose emails answer it.
GOLDEN_QUERIES: list[tuple[str, set[str]]] = [
    ("When is the Q3 planning doc due?", {"wk-1"}),
    ("What happened with the API latency incident postmortem?", {"wk-2"}),
    ("Can you review the vendor contract liability clause?", {"wk-3"}),
    ("When will my BookNest book order arrive?", {"rc-1", "rc-6"}),
    ("Dinner plans with Alice this weekend", {"ps-1"}),
    ("Did CI pass on the api repo?", {"nt-2"}),
    ("Is there a phishing email about my account being suspended?", {"sp-2"}),
    ("Photos from the hiking trip", {"ps-2"}),
]


@dataclass(frozen=True)
class RetrievalResult:
    """Aggregate retrieval metrics over the golden query set."""

    k: int
    n_queries: int
    recall_at_k: float  # mean fraction of relevant emails found in the top k
    mrr: float  # mean reciprocal rank of the first relevant email
    hit_rate: float  # fraction of queries with >=1 relevant email in the top k


def evaluate_retrieval(retriever: Retriever, emails: list[Email], k: int = 5) -> RetrievalResult:
    """Score ``retriever`` on :data:`GOLDEN_QUERIES` using ``emails`` as truth."""
    retriever.index(emails)
    recalls, reciprocal_ranks, hits = [], [], 0

    for question, thread_ids in GOLDEN_QUERIES:
        relevant = {e.message_id for e in emails if e.thread_id in thread_ids}
        if not relevant:
            continue
        ranked_ids = [hit.email.message_id for hit in retriever.search(question, k=k)]

        found = relevant.intersection(ranked_ids)
        recalls.append(len(found) / len(relevant))
        if found:
            hits += 1
        first = next((i for i, mid in enumerate(ranked_ids, start=1) if mid in relevant), None)
        reciprocal_ranks.append(1.0 / first if first else 0.0)

    n = len(recalls) or 1
    return RetrievalResult(
        k=k,
        n_queries=len(recalls),
        recall_at_k=sum(recalls) / n,
        mrr=sum(reciprocal_ranks) / n,
        hit_rate=hits / n,
    )


def render_retrieval(result: RetrievalResult) -> str:
    return "\n".join(
        [
            f"Retrieval eval (bm25) — {result.n_queries} golden queries, k={result.k}",
            f"  recall@{result.k}   {result.recall_at_k:.2f}",
            f"  MRR         {result.mrr:.2f}",
            f"  hit-rate    {result.hit_rate:.2f}",
        ]
    )
