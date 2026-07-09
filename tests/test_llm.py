"""Tests for the LLM client + retry helper (no network)."""

from __future__ import annotations

import pytest

from inbox_agent.llm.openai_client import _is_retryable
from inbox_agent.llm.retry import RetryExhausted, with_retries


class Boom(Exception):
    pass


def test_with_retries_succeeds_after_transient_failures():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Boom()
        return "ok"

    out = with_retries(
        fn, is_retryable=lambda e: isinstance(e, Boom), max_retries=5, sleep=lambda _s: None
    )
    assert out == "ok"
    assert calls["n"] == 3


def test_with_retries_gives_up_after_max():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        raise Boom()

    with pytest.raises(RetryExhausted):
        with_retries(fn, is_retryable=lambda _e: True, max_retries=2, sleep=lambda _s: None)
    # initial try + 2 retries
    assert attempts["n"] == 3


def test_with_retries_propagates_non_retryable():
    def fn():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        with_retries(fn, is_retryable=lambda _e: False, sleep=lambda _s: None)


def test_is_retryable_ignores_ordinary_errors():
    assert _is_retryable(ValueError("x")) is False


def test_openai_client_complete_returns_text(monkeypatch):
    import openai

    class FakeMsg:
        content = "  work  "

    class FakeChoice:
        message = FakeMsg()

    class FakeResp:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            # Assert we pass the messages through in the expected shape.
            assert kwargs["messages"][0]["role"] == "system"
            assert kwargs["messages"][1]["role"] == "user"
            return FakeResp()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    from inbox_agent.llm.openai_client import OpenAICompatibleClient

    client = OpenAICompatibleClient(base_url="http://local", api_key="k", model="m")
    assert client.complete(system="s", user="u") == "work"  # stripped
    assert client.model == "m"
