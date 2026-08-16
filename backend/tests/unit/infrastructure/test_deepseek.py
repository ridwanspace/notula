from types import SimpleNamespace
from typing import Any, cast

import httpx
import openai
import pytest
from openai import AsyncOpenAI

from notula.infrastructure.providers.deepseek import DeepSeekCompleter


def _response(text: str = '{"ok": true}') -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def _http_error(status: int, message: str) -> httpx.Response:
    return httpx.Response(
        status,
        request=httpx.Request("POST", "https://api.example.test/chat/completions"),
        json={"error": {"message": message}},
    )


class StubCompletions:
    def __init__(self, effects: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._effects = effects

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


def _client(effects: list[Any]) -> tuple[AsyncOpenAI, StubCompletions]:
    completions = StubCompletions(effects)
    stub = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return cast(AsyncOpenAI, stub), completions


async def test_happy_path_uses_json_mode() -> None:
    client, completions = _client([_response()])
    completer = DeepSeekCompleter("key", "deepseek-v4-flash", client=client)
    completion = await completer.complete_json("sys", "user")
    assert completion.text == '{"ok": true}'
    assert completion.usage.input_tokens == 11
    assert completion.usage.output_tokens == 7
    assert completion.model == "deepseek-v4-flash"
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


async def test_falls_back_when_parameter_rejected_and_remembers() -> None:
    rejected = openai.BadRequestError(
        "Error code: 400 - unsupported parameter: response_format",
        response=_http_error(400, "unsupported parameter: response_format"),
        body=None,
    )
    client, completions = _client([rejected, _response(), _response()])
    completer = DeepSeekCompleter("key", "deepseek-v4-flash", client=client)

    first = await completer.complete_json("sys", "user")
    assert first.text == '{"ok": true}'
    assert "response_format" not in completions.calls[1]

    # Capability is remembered: no further probe with response_format.
    await completer.complete_json("sys", "again")
    assert "response_format" not in completions.calls[2]
    assert len(completions.calls) == 3


async def test_unrelated_bad_request_propagates() -> None:
    rejected = openai.BadRequestError(
        "Error code: 400 - model not found",
        response=_http_error(400, "model not found"),
        body=None,
    )
    client, _ = _client([rejected])
    completer = DeepSeekCompleter("key", "deepseek-v4-flash", client=client)
    with pytest.raises(openai.BadRequestError):
        await completer.complete_json("sys", "user")


async def test_server_error_never_triggers_fallback() -> None:
    # A 5xx mentioning response_format is an outage, not a missing capability.
    outage = openai.InternalServerError(
        "Error code: 500 - response_format processing crashed",
        response=_http_error(500, "response_format processing crashed"),
        body=None,
    )
    client, completions = _client([outage])
    completer = DeepSeekCompleter("key", "deepseek-v4-flash", client=client)
    with pytest.raises(openai.InternalServerError):
        await completer.complete_json("sys", "user")
    assert len(completions.calls) == 1
