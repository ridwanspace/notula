"""DeepSeek chat adapter for pass-2 summarization (OpenAI-compatible surface)."""

from __future__ import annotations

from typing import Any

import openai
from openai import AsyncOpenAI

from notula.application.ports import Completion
from notula.domain.models import TokenUsage


class DeepSeekCompleter:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        client: AsyncOpenAI | None = None,
    ) -> None:
        # Explicit timeout: a stalled connection must fail the stage loudly
        # instead of wedging the worker forever (seen with blackholed IPv6).
        self._client = client or AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=120.0, max_retries=2
        )
        self._model = model
        self._supports_json_mode = True

    @property
    def model(self) -> str:
        return self._model

    async def complete_json(self, system: str, user: str) -> Completion:
        messages: Any = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if self._supports_json_mode:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
                return self._to_completion(response)
            except openai.BadRequestError as exc:
                # Fall back only on a 4xx that names the *parameter* — never match
                # vendor prose, and never catch 5xx: an outage must not be
                # mistaken for a missing capability.
                if "response_format" not in str(exc):
                    raise
                self._supports_json_mode = False
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.0,
        )
        return self._to_completion(response)

    def _to_completion(self, response: Any) -> Completion:
        usage = getattr(response, "usage", None)
        return Completion(
            text=response.choices[0].message.content or "",
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            ),
            model=self._model,
        )
