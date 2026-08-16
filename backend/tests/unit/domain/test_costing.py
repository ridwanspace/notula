import pytest

from notula.domain.costing import (
    GEMINI_AUDIO_TOKENS_PER_SECOND,
    cost_usd,
    estimate_audio_tokens,
)
from notula.domain.models import TokenUsage


class TestEstimateAudioTokens:
    def test_one_minute(self) -> None:
        assert estimate_audio_tokens(60.0) == 60 * GEMINI_AUDIO_TOKENS_PER_SECOND

    def test_zero(self) -> None:
        assert estimate_audio_tokens(0.0) == 0

    def test_fractional_seconds_round_up(self) -> None:
        assert estimate_audio_tokens(0.5) == 16
        assert estimate_audio_tokens(1.01) == 33

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="duration_seconds"):
            estimate_audio_tokens(-1.0)


class TestCostUsd:
    def test_input_only(self) -> None:
        assert cost_usd("gemini-3.5-flash", TokenUsage(1_000_000, 0)) == pytest.approx(1.50)

    def test_output_only(self) -> None:
        assert cost_usd("gemini-3.5-flash", TokenUsage(0, 1_000_000)) == pytest.approx(9.00)

    def test_combined(self) -> None:
        assert cost_usd("deepseek-v4-flash", TokenUsage(1_000_000, 1_000_000)) == pytest.approx(
            0.42
        )

    def test_small_usage(self) -> None:
        assert cost_usd("deepseek-v4-flash", TokenUsage(1000, 500)) == pytest.approx(
            (1000 * 0.14 + 500 * 0.28) / 1_000_000
        )

    def test_mock_is_free(self) -> None:
        assert cost_usd("mock", TokenUsage(10_000, 10_000)) == 0.0

    def test_unknown_model_is_none_not_zero(self) -> None:
        assert cost_usd("some-new-model", TokenUsage(1000, 1000)) is None
