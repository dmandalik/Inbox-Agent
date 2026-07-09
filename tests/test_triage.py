"""Tests for the triage classifiers (stub rules + zero-shot LLM, mocked)."""

from __future__ import annotations

import pytest

from inbox_agent.config import ConfigError, Settings
from inbox_agent.llm.base import LLMClient
from inbox_agent.models import Email
from inbox_agent.synthetic import generate_corpus
from inbox_agent.triage import CATEGORIES, build_classifier
from inbox_agent.triage.llm import SYSTEM_PROMPT, LLMClassifier, _parse_category
from inbox_agent.triage.stub import StubClassifier


# --- Stub classifier -------------------------------------------------------
def test_stub_returns_valid_categories_only():
    clf = StubClassifier()
    for e in generate_corpus():
        assert clf.classify(e) in CATEGORIES


def test_stub_is_accurate_on_synthetic_corpus():
    clf = StubClassifier()
    emails = generate_corpus()
    correct = sum(1 for e in emails if clf.classify(e) == e.category)
    acc = correct / len(emails)
    # The stub is tuned to this taxonomy; it should be strong here.
    assert acc >= 0.9, f"stub accuracy too low: {acc:.2f}"


def test_stub_flags_all_injection_samples_as_spam():
    clf = StubClassifier()
    injections = [
        e
        for e in generate_corpus()
        if "ignore all previous instructions" in e.body.lower()
        or "system override" in e.body.lower()
    ]
    assert injections
    assert all(clf.classify(e) == "spam_phishing" for e in injections)


def test_stub_is_deterministic():
    clf = StubClassifier()
    e = generate_corpus()[0]
    assert clf.classify(e) == clf.classify(e)


# --- LLM classifier (mocked client; NO network) ----------------------------
class FakeLLMClient(LLMClient):
    """Returns a scripted reply and records the last prompt it received."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.model = "fake"
        self.last_system = None
        self.last_user = None

    def complete(self, *, system, user, temperature=0.0, max_tokens=512) -> str:
        self.last_system = system
        self.last_user = user
        return self.reply


def _email() -> Email:
    return Email(
        message_id="m1",
        thread_id="t1",
        date="2026-06-15T09:00:00+00:00",
        from_addr="someone@example.com",
        from_name="Someone",
        subject="Hi",
        body="hello",
    )


def test_llm_classifier_returns_model_label():
    clf = LLMClassifier(FakeLLMClient("work"))
    assert clf.classify(_email()) == "work"


def test_llm_classifier_parses_noisy_reply():
    clf = LLMClassifier(FakeLLMClient("Category: receipt_order.\n"))
    assert clf.classify(_email()) == "receipt_order"


def test_llm_classifier_clamps_garbage_to_default():
    clf = LLMClassifier(FakeLLMClient("banana"))
    assert clf.classify(_email()) == "notification"  # DEFAULT_CATEGORY


def test_llm_prompt_wraps_body_and_marks_untrusted():
    fake = FakeLLMClient("work")
    LLMClassifier(fake).classify(_email())
    assert "<email>" in fake.last_user and "</email>" in fake.last_user
    assert "UNTRUSTED DATA" in SYSTEM_PROMPT


def test_parse_category_helpers():
    assert _parse_category("SPAM_PHISHING") == "spam_phishing"
    assert _parse_category("this looks like personal mail") == "personal"
    assert _parse_category("") == "notification"


# --- Factory / config ------------------------------------------------------
def test_factory_builds_stub_without_any_key():
    settings = Settings(triage_backend="stub", _env_file=None)
    clf = build_classifier(settings)
    assert clf.name == "stub"


def test_factory_llm_without_key_fails_loudly():
    settings = Settings(
        triage_backend="llm",
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
        _env_file=None,
    )
    with pytest.raises(ConfigError, match="TRIAGE_BACKEND=stub"):
        build_classifier(settings)


def test_factory_rejects_unknown_backend():
    settings = Settings(triage_backend="stub", _env_file=None)
    settings = settings.model_copy(update={"triage_backend": "magic"})
    with pytest.raises(ValueError, match="unknown TRIAGE_BACKEND"):
        build_classifier(settings)
