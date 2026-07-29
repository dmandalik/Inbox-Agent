"""BM25 retrieval + retrieval metrics over the synthetic corpus."""

from __future__ import annotations

import pytest

from inbox_agent.retrieval import (
    GOLDEN_QUERIES,
    BM25Retriever,
    build_retriever,
    evaluate_retrieval,
    tokenize,
)
from inbox_agent.synthetic import generate_corpus


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("The Q3 Planning DOC is due") == ["q3", "planning", "doc", "due"]


def test_empty_and_stopword_only_queries_return_nothing():
    r = BM25Retriever()
    r.index(generate_corpus())
    assert r.search("") == []
    assert r.search("the is to") == []  # all stopwords


def test_search_over_empty_inbox_is_safe():
    r = BM25Retriever()
    r.index([])
    assert r.search("anything") == []


def test_finds_the_relevant_thread_top():
    r = build_retriever("bm25")
    r.index(generate_corpus())
    hits = r.search("Q3 planning doc review", k=3)
    assert hits
    # The top hit should be from the Q3 planning thread.
    assert hits[0].email.thread_id == "wk-1"
    assert hits[0].score > 0


def test_search_respects_k_and_orders_by_score():
    r = build_retriever("bm25")
    r.index(generate_corpus())
    hits = r.search("order shipped delivery", k=4)
    assert len(hits) <= 4
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_sender_query_matches_by_from_name():
    r = build_retriever("bm25")
    r.index(generate_corpus())
    hits = r.search("Alice dinner ramen", k=3)
    assert any(h.email.from_name == "Alice Ramirez" for h in hits)


def test_is_deterministic():
    r1, r2 = build_retriever("bm25"), build_retriever("bm25")
    corpus = generate_corpus()
    r1.index(corpus)
    r2.index(corpus)
    ids1 = [h.email.message_id for h in r1.search("vendor contract", k=5)]
    ids2 = [h.email.message_id for h in r2.search("vendor contract", k=5)]
    assert ids1 == ids2


def test_build_retriever_rejects_unknown():
    with pytest.raises(ValueError, match="unknown retriever"):
        build_retriever("dense")


# --- retrieval metrics -----------------------------------------------------


def test_evaluate_retrieval_is_strong_on_synthetic():
    result = evaluate_retrieval(build_retriever("bm25"), generate_corpus(), k=5)
    assert result.n_queries == len(GOLDEN_QUERIES)
    # BM25 should comfortably find the relevant thread for these keyword queries.
    assert result.hit_rate >= 0.8
    assert result.mrr >= 0.7
    assert 0.0 <= result.recall_at_k <= 1.0


def test_recall_improves_or_holds_with_larger_k():
    small = evaluate_retrieval(build_retriever("bm25"), generate_corpus(), k=3)
    large = evaluate_retrieval(build_retriever("bm25"), generate_corpus(), k=10)
    assert large.recall_at_k >= small.recall_at_k
