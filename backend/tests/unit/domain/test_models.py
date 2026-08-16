from notula.domain.models import TokenUsage, Transcript, Utterance


def test_token_usage_addition() -> None:
    assert TokenUsage(1, 2) + TokenUsage(3, 4) == TokenUsage(4, 6)


def test_token_usage_defaults_to_zero() -> None:
    assert TokenUsage() == TokenUsage(0, 0)


def test_as_text_renders_mm_ss_lines() -> None:
    transcript = Transcript(
        utterances=(
            Utterance(0.0, "Rina", "selamat pagi semua"),
            Utterance(65.9, "Speaker 2", "quick update from me"),
        ),
        duration_seconds=90.0,
    )
    assert transcript.as_text() == (
        "[00:00] Rina: selamat pagi semua\n[01:05] Speaker 2: quick update from me"
    )


def test_speakers_deduplicated_in_first_seen_order() -> None:
    transcript = Transcript(
        utterances=(
            Utterance(0.0, "B", "x"),
            Utterance(1.0, "A", "y"),
            Utterance(2.0, "B", "z"),
        ),
        duration_seconds=5.0,
    )
    assert transcript.speakers() == ("B", "A")
