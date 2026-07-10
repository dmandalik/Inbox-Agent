"""The retry helper and the OpenAI-compatible client. No network."""

from __future__ import annotations

import pytest

from inbox_agent.llm import RetryExhausted, _is_retryable, with_retries


class Transient(Exception):
    pass


def never_sleep(_seconds: float) -> None:
    """Injected so backoff tests run instantly."""


def test_retries_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise Transient()
        return "ok"

    result = with_retries(flaky, is_retryable=lambda e: isinstance(e, Transient), sleep=never_sleep)
    assert result == "ok"
    assert len(calls) == 3


def test_gives_up_after_max_retries():
    calls = []

    def always_fails():
        calls.append(1)
        raise Transient()

    with pytest.raises(RetryExhausted):
        with_retries(always_fails, is_retryable=lambda _e: True, max_retries=2, sleep=never_sleep)
    assert len(calls) == 3  # initial attempt + 2 retries


def test_non_retryable_errors_propagate_immediately():
    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        with_retries(boom, is_retryable=lambda _e: False, sleep=never_sleep)


def test_ordinary_errors_are_not_retryable():
    assert _is_retryable(ValueError("x")) is False


def test_openai_client_sends_system_and_user_and_strips_the_reply(monkeypatch):
    import openai

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["messages"][0]["role"] == "system"
            assert kwargs["messages"][1]["role"] == "user"
            message = type("M", (), {"content": "  work  "})
            choice = type("C", (), {"message": message})
            return type("R", (), {"choices": [choice]})

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    from inbox_agent.llm import OpenAICompatibleClient

    client = OpenAICompatibleClient(base_url="http://local", api_key="k", model="m")
    assert client.complete(system="s", user="u") == "work"
    assert client.model == "m"
