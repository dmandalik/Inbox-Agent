"""Both classifiers. The LLM one is mocked — no unit test touches the network."""

from __future__ import annotations

import pytest

from inbox_agent.config import ConfigError, Settings
from inbox_agent.llm import LLMClient
from inbox_agent.models import Email
from inbox_agent.synthetic import generate_corpus
from inbox_agent.triage import (
    CATEGORIES,
    SYSTEM_PROMPT,
    LLMClassifier,
    StubClassifier,
    _parse_category,
    build_classifier,
)


def an_email(**overrides) -> Email:
    defaults = {
        "message_id": "m1",
        "thread_id": "t1",
        "date": "2026-06-15T09:00:00+00:00",
        "from_addr": "someone@example.com",
        "from_name": "Someone",
        "subject": "Hi",
        "body": "hello",
    }
    return Email(**{**defaults, **overrides})


# --- stub backend ----------------------------------------------------------
def test_stub_only_ever_returns_valid_categories():
    stub = StubClassifier()
    assert all(stub.classify(e) in CATEGORIES for e in generate_corpus())


def test_stub_is_accurate_on_the_corpus():
    stub = StubClassifier()
    emails = generate_corpus()
    correct = sum(1 for e in emails if stub.classify(e) == e.category)
    # Tuned to this taxonomy, so this is a floor/regression guard, not a result.
    assert correct / len(emails) >= 0.9


def test_stub_flags_every_injection_sample_as_spam():
    stub = StubClassifier()
    injections = [e for e in generate_corpus() if "ignore all previous" in e.body.lower()]
    assert injections
    assert all(stub.classify(e) == "spam_phishing" for e in injections)


def test_stub_is_deterministic():
    stub, email = StubClassifier(), generate_corpus()[0]
    assert stub.classify(email) == stub.classify(email)


def test_stub_falls_back_to_default_for_an_unrecognisable_email():
    assert StubClassifier().classify(an_email(from_addr="x@unknown.example.com")) == "notification"


# --- llm backend (mocked) --------------------------------------------------
class FakeLLM(LLMClient):
    """Returns a scripted reply and records the prompt it was given."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.model = "fake"
        self.system = self.user = ""

    def complete(self, *, system: str, user: str, max_tokens: int = 512) -> str:
        self.system, self.user = system, user
        return self.reply


def test_llm_classifier_returns_the_models_label():
    assert LLMClassifier(FakeLLM("work")).classify(an_email()) == "work"


def test_llm_classifier_parses_a_noisy_reply():
    assert (
        LLMClassifier(FakeLLM("Category: receipt_order.\n")).classify(an_email()) == "receipt_order"
    )


def test_llm_classifier_clamps_garbage_to_the_default():
    assert LLMClassifier(FakeLLM("banana")).classify(an_email()) == "notification"


def test_llm_prompt_delimits_the_email_and_marks_it_untrusted():
    fake = FakeLLM("work")
    LLMClassifier(fake).classify(an_email())
    assert "<email>" in fake.user and "</email>" in fake.user
    assert "UNTRUSTED DATA" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("SPAM_PHISHING", "spam_phishing"),
        ("looks personal to me", "personal"),
        ("", "notification"),
    ],
)
def test_parse_category(reply, expected):
    assert _parse_category(reply) == expected


# --- backend selection -----------------------------------------------------
def settings(**overrides) -> Settings:
    # _env_file=None so a developer's local .env can never leak a real key in.
    return Settings(_env_file=None, **overrides)


def test_stub_backend_needs_no_key():
    assert build_classifier(settings(triage_backend="stub")).name == "stub"


def test_llm_backend_without_a_key_fails_loudly():
    unconfigured = settings(
        triage_backend="llm", llm_base_url=None, llm_api_key=None, llm_model=None
    )
    with pytest.raises(ConfigError, match="TRIAGE_BACKEND=stub"):
        build_classifier(unconfigured)


def test_unknown_backend_is_rejected():
    bad = settings(triage_backend="stub").model_copy(update={"triage_backend": "magic"})
    with pytest.raises(ValueError, match="unknown TRIAGE_BACKEND"):
        build_classifier(bad)
