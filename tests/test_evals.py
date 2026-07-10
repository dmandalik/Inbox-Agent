"""Tests for the eval metrics + harness."""

from __future__ import annotations

import pytest

from inbox_agent.evals import evaluate
from inbox_agent.evals.metrics import (
    accuracy,
    confusion_matrix,
    macro_average,
    precision_recall_f1,
)

LABELS = ["a", "b", "c"]


def test_perfect_predictions_score_1():
    y = ["a", "b", "c", "a"]
    per_class = precision_recall_f1(y, y, LABELS)
    assert all(m.f1 == 1.0 for m in per_class.values() if m.support)
    assert accuracy(y, y) == 1.0


def test_precision_recall_on_known_case():
    # true:  a a b
    # pred:  a b b   -> for 'a': tp=1, fn=1  ; for 'b': tp=1, fp=1
    y_true = ["a", "a", "b"]
    y_pred = ["a", "b", "b"]
    m = precision_recall_f1(y_true, y_pred, ["a", "b"])
    assert m["a"].precision == pytest.approx(1.0)  # 1 tp, 0 fp
    assert m["a"].recall == pytest.approx(0.5)  # 1 tp, 1 fn
    assert m["b"].precision == pytest.approx(0.5)  # 1 tp, 1 fp
    assert m["b"].recall == pytest.approx(1.0)
    assert m["a"].f1 == pytest.approx(2 / 3)


def test_confusion_matrix_counts():
    y_true = ["a", "a", "b", "c"]
    y_pred = ["a", "b", "b", "a"]
    cm = confusion_matrix(y_true, y_pred, LABELS)
    assert cm["a"]["a"] == 1
    assert cm["a"]["b"] == 1
    assert cm["b"]["b"] == 1
    assert cm["c"]["a"] == 1
    # Row sums equal true support.
    assert sum(cm["a"].values()) == 2


def test_zero_support_class_is_present_and_zero():
    y_true = ["a", "a"]
    y_pred = ["a", "a"]
    m = precision_recall_f1(y_true, y_pred, ["a", "b"])
    assert m["b"].support == 0
    assert m["b"].precision == 0.0 and m["b"].recall == 0.0 and m["b"].f1 == 0.0


def test_macro_average():
    y_true = ["a", "b"]
    y_pred = ["a", "a"]
    per_class = precision_recall_f1(y_true, y_pred, ["a", "b"])
    p, r, f = macro_average(per_class)
    # a: prec .5 rec 1 ; b: prec 0 rec 0
    assert p == pytest.approx(0.25)
    assert r == pytest.approx(0.5)


def test_evaluate_aligns_on_shared_ids():
    gt = {"m1": "a", "m2": "b", "m3": "c"}
    pred = {"m1": "a", "m2": "b"}  # m3 not predicted -> excluded
    result = evaluate(gt, pred, labels=LABELS, backend="test")
    assert result.n == 2
    assert result.accuracy == 1.0
    assert result.backend == "test"


def test_evaluate_raises_on_no_overlap():
    with pytest.raises(ValueError, match="No overlapping"):
        evaluate({"m1": "a"}, {"m2": "b"}, labels=LABELS)


def test_evaluate_mismatched_lengths_are_handled_via_ids():
    # Predictions can be a subset; harness aligns by id, not by position.
    gt = {"m1": "a", "m2": "b"}
    pred = {"m2": "a"}  # wrong prediction for m2
    result = evaluate(gt, pred, labels=LABELS)
    assert result.n == 1
    assert result.accuracy == 0.0
