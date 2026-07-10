"""Eval metrics, worked by hand so the numbers are checkable."""

from __future__ import annotations

import pytest

from inbox_agent.evals import evaluate

LABELS = ["a", "b", "c"]


def test_perfect_predictions_score_one():
    truth = {"1": "a", "2": "b", "3": "c"}
    result = evaluate(truth, truth, labels=LABELS)
    assert result.accuracy == 1.0
    assert all(result.per_class[label].f1 == 1.0 for label in LABELS)


def test_precision_and_recall_on_a_worked_example():
    # true:  a a b     for 'a': tp=1, fn=1  -> prec 1.00, recall 0.50
    # pred:  a b b     for 'b': tp=1, fp=1  -> prec 0.50, recall 1.00
    truth = {"1": "a", "2": "a", "3": "b"}
    preds = {"1": "a", "2": "b", "3": "b"}
    m = evaluate(truth, preds, labels=["a", "b"]).per_class

    assert m["a"].precision == pytest.approx(1.0)
    assert m["a"].recall == pytest.approx(0.5)
    assert m["a"].f1 == pytest.approx(2 / 3)
    assert m["b"].precision == pytest.approx(0.5)
    assert m["b"].recall == pytest.approx(1.0)


def test_confusion_matrix_counts():
    truth = {"1": "a", "2": "a", "3": "b", "4": "c"}
    preds = {"1": "a", "2": "b", "3": "b", "4": "a"}
    cm = evaluate(truth, preds, labels=LABELS).confusion

    assert cm["a"]["a"] == 1
    assert cm["a"]["b"] == 1  # one 'a' misread as 'b'
    assert cm["c"]["a"] == 1
    assert sum(cm["a"].values()) == 2  # row sum == support of 'a'


def test_a_class_with_no_examples_still_appears_as_zero():
    truth = {"1": "a", "2": "a"}
    m = evaluate(truth, truth, labels=["a", "b"]).per_class
    assert m["b"].support == 0
    assert (m["b"].precision, m["b"].recall, m["b"].f1) == (0.0, 0.0, 0.0)


def test_macro_average_is_unweighted():
    truth = {"1": "a", "2": "b"}
    preds = {"1": "a", "2": "a"}  # a: prec .5 rec 1 ; b: prec 0 rec 0
    result = evaluate(truth, preds, labels=["a", "b"])
    assert result.macro_precision == pytest.approx(0.25)
    assert result.macro_recall == pytest.approx(0.5)


def test_only_ids_present_in_both_maps_are_scored():
    truth = {"1": "a", "2": "b", "3": "c"}
    preds = {"1": "a", "2": "b"}  # '3' was never triaged
    result = evaluate(truth, preds, labels=LABELS)
    assert result.n == 2
    assert result.accuracy == 1.0


def test_no_overlap_raises():
    with pytest.raises(ValueError, match="No overlapping"):
        evaluate({"1": "a"}, {"2": "b"}, labels=LABELS)


def test_backend_is_reported():
    truth = {"1": "a"}
    assert evaluate(truth, truth, labels=LABELS, backend="stub").backend == "stub"
