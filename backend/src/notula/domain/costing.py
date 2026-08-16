"""Token-cost model.

Costs are computed from the token counts the providers actually reported
(usage metadata), multiplied by a published price table — never from guesses.
An unknown model yields None, which the API surfaces as "cost unknown" rather
than silently reporting $0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from notula.domain.models import TokenUsage

# Gemini bills audio at a fixed token rate per second of audio:
# https://ai.google.dev/gemini-api/docs/audio
GEMINI_AUDIO_TOKENS_PER_SECOND = 32


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_usd_per_million: float
    output_usd_per_million: float


# Prices retrieved 2026-08-16 (USD per 1M tokens, standard tier, cache-miss input):
# - Gemini: https://ai.google.dev/gemini-api/docs/pricing
# - DeepSeek: https://deepseek.ai/pricing
PRICES: Mapping[str, ModelPrice] = {
    "gemini-3.5-flash": ModelPrice(1.50, 9.00),
    "gemini-3.5-flash-lite": ModelPrice(0.30, 2.50),
    "deepseek-v4-flash": ModelPrice(0.14, 0.28),
    "mock": ModelPrice(0.0, 0.0),
}


def estimate_audio_tokens(duration_seconds: float) -> int:
    """Estimated Gemini input tokens for an audio segment (32 tokens/second)."""
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be >= 0")
    return math.ceil(duration_seconds * GEMINI_AUDIO_TOKENS_PER_SECOND)


def cost_usd(model: str, usage: TokenUsage) -> float | None:
    """Cost of a call from reported usage, or None when the model is unpriced."""
    price = PRICES.get(model)
    if price is None:
        return None
    return (
        usage.input_tokens * price.input_usd_per_million
        + usage.output_tokens * price.output_usd_per_million
    ) / 1_000_000
