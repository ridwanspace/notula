import pytest

from notula.domain.chunking import Chunk, merge_transcripts, plan_chunks
from notula.domain.models import Transcript, Utterance


def _transcript(*utterances: tuple[float, str, str], duration: float = 0.0) -> Transcript:
    return Transcript(
        utterances=tuple(Utterance(s, sp, t) for s, sp, t in utterances),
        duration_seconds=duration,
    )


class TestPlanChunks:
    def test_short_audio_is_a_single_chunk(self) -> None:
        chunks = plan_chunks(100.0)
        assert chunks == (Chunk(0, 0.0, 100.0),)

    def test_exactly_max_is_a_single_chunk(self) -> None:
        chunks = plan_chunks(1000.0, max_chunk_seconds=1000.0)
        assert len(chunks) == 1

    def test_long_audio_splits_with_overlap(self) -> None:
        chunks = plan_chunks(2500.0, max_chunk_seconds=1000.0, overlap_seconds=10.0)
        assert chunks == (
            Chunk(0, 0.0, 1000.0),
            Chunk(1, 990.0, 2000.0),
            Chunk(2, 1990.0, 2500.0),
        )

    def test_boundary_snaps_to_silence_within_window(self) -> None:
        chunks = plan_chunks(
            2500.0,
            max_chunk_seconds=1000.0,
            overlap_seconds=10.0,
            snap_window_seconds=30.0,
            silence_points=(980.0, 1990.0),
        )
        # 980 is inside [970, 1000] and snaps; 1990 is past the next target
        # (1980) so that boundary stays a hard cut.
        assert chunks == (
            Chunk(0, 0.0, 980.0),
            Chunk(1, 970.0, 1980.0),
            Chunk(2, 1970.0, 2500.0),
        )

    def test_silence_outside_snap_window_is_ignored(self) -> None:
        chunks = plan_chunks(
            1500.0,
            max_chunk_seconds=1000.0,
            overlap_seconds=10.0,
            snap_window_seconds=30.0,
            silence_points=(900.0,),
        )
        assert chunks[0].end_seconds == 1000.0

    def test_closest_silence_below_target_wins(self) -> None:
        chunks = plan_chunks(
            1500.0,
            max_chunk_seconds=1000.0,
            snap_window_seconds=30.0,
            silence_points=(975.0, 995.0),
        )
        assert chunks[0].end_seconds == 995.0

    @pytest.mark.parametrize("duration", [0.0, -5.0])
    def test_non_positive_duration_rejected(self, duration: float) -> None:
        with pytest.raises(ValueError, match="duration_seconds"):
            plan_chunks(duration)

    def test_negative_overlap_rejected(self) -> None:
        with pytest.raises(ValueError, match="overlap_seconds"):
            plan_chunks(100.0, overlap_seconds=-1.0)

    def test_overlap_close_to_chunk_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="overlap_seconds"):
            plan_chunks(100.0, max_chunk_seconds=60.0, overlap_seconds=30.0)

    def test_snap_window_close_to_chunk_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="snap_window_seconds"):
            plan_chunks(100.0, max_chunk_seconds=40.0, overlap_seconds=5.0)

    def test_chunk_duration_property(self) -> None:
        assert Chunk(0, 10.0, 35.0).duration_seconds == 25.0


class TestMergeTranscripts:
    def test_empty_parts_rejected(self) -> None:
        with pytest.raises(ValueError, match="no transcript parts"):
            merge_transcripts([])

    def test_single_part_passes_through(self) -> None:
        part = _transcript((5.0, "Alice", "hello"), (20.0, "Bob", "hi"))
        merged = merge_transcripts([(Chunk(0, 0.0, 60.0), part)])
        assert merged.utterances == part.utterances
        assert merged.duration_seconds == 60.0

    def test_later_chunk_timestamps_are_offset(self) -> None:
        c0 = _transcript((10.0, "Alice", "opening"))
        c1 = _transcript((30.0, "Bob", "later point"))  # chunk-relative
        merged = merge_transcripts(
            [(Chunk(0, 0.0, 100.0), c0), (Chunk(1, 90.0, 180.0), c1)],
            overlap_seconds=10.0,
        )
        assert [u.start_seconds for u in merged.utterances] == [10.0, 120.0]
        assert merged.duration_seconds == 180.0

    def test_overlap_duplicates_dropped_at_midpoint(self) -> None:
        # Overlap window is [90, 100]; midpoint 95. The shared line at 92 must
        # survive exactly once (from the earlier chunk).
        c0 = _transcript(
            (10.0, "Alice", "intro"),
            (92.0, "Alice", "shared line"),
            (97.0, "Bob", "tail line"),
        )
        c1 = _transcript(
            (2.0, "Alice", "shared line"),  # abs 92 — duplicate, dropped
            (7.0, "Bob", "tail line"),  # abs 97 — kept from this chunk
            (30.0, "Alice", "new point"),  # abs 120
        )
        merged = merge_transcripts(
            [(Chunk(0, 0.0, 100.0), c0), (Chunk(1, 90.0, 180.0), c1)],
            overlap_seconds=10.0,
        )
        texts = [u.text for u in merged.utterances]
        assert texts == ["intro", "shared line", "tail line", "new point"]

    def test_generic_speakers_mapped_via_overlap_text(self) -> None:
        c0 = _transcript(
            (40.0, "Speaker 2", "earlier point"),
            (91.0, "Speaker 1", "Let's review the budget"),
        )
        # The second chunk diarized the same voice as "Speaker 2".
        c1 = _transcript(
            (1.0, "Speaker 2", "Let's review the budget!"),  # abs 91, matches c0
            (20.0, "Speaker 2", "next item"),  # abs 110
        )
        merged = merge_transcripts(
            [(Chunk(0, 0.0, 100.0), c0), (Chunk(1, 90.0, 180.0), c1)],
            overlap_seconds=10.0,
        )
        by_time = {u.start_seconds: u.speaker for u in merged.utterances}
        assert by_time[110.0] == "Speaker 1"

    def test_unmatched_generic_speaker_gets_fresh_label(self) -> None:
        c0 = _transcript(
            (40.0, "Speaker 1", "earlier point"),
            (91.0, "Speaker 2", "handover sentence"),
        )
        c1 = _transcript(
            (1.0, "Speaker 1", "handover sentence"),  # abs 91 -> maps to Speaker 2
            (25.0, "Speaker 2", "a brand new voice"),  # abs 115, never overlapped
        )
        merged = merge_transcripts(
            [(Chunk(0, 0.0, 100.0), c0), (Chunk(1, 90.0, 180.0), c1)],
            overlap_seconds=10.0,
        )
        by_time = {u.start_seconds: u.speaker for u in merged.utterances}
        assert by_time[91.0] == "Speaker 2"
        # The unmatched voice must not collide with existing labels.
        assert by_time[115.0] == "Speaker 3"

    def test_named_speakers_pass_through_unmapped(self) -> None:
        c0 = _transcript((91.0, "Rina", "handover sentence"))
        c1 = _transcript((25.0, "Dimas", "closing remarks"))
        merged = merge_transcripts(
            [(Chunk(0, 0.0, 100.0), c0), (Chunk(1, 90.0, 180.0), c1)],
            overlap_seconds=10.0,
        )
        assert {u.speaker for u in merged.utterances} == {"Rina", "Dimas"}

    def test_result_sorted_by_time(self) -> None:
        c0 = _transcript((50.0, "Alice", "b"), (10.0, "Alice", "a"))
        merged = merge_transcripts([(Chunk(0, 0.0, 60.0), c0)])
        assert [u.text for u in merged.utterances] == ["a", "b"]


def test_merge_overlap_speaker_with_unmatched_text_gets_fresh_label() -> None:
    """A generic speaker who talks in the overlap but whose words match nothing
    from the earlier chunk cannot be proven identical — renumbered instead."""
    chunk_a = Chunk(0, 0.0, 30.0)
    chunk_b = Chunk(1, 15.0, 45.0)
    part_a = Transcript(
        utterances=(Utterance(20.0, "Speaker 1", "we ship on friday"),),
        duration_seconds=30.0,
    )
    part_b = Transcript(
        utterances=(
            Utterance(1.0, "Speaker 1", "completely different words"),
            Utterance(20.0, "Speaker 1", "later in the second chunk"),
        ),
        duration_seconds=30.0,
    )
    merged = merge_transcripts([(chunk_a, part_a), (chunk_b, part_b)], overlap_seconds=15.0)
    speakers = {u.speaker for u in merged.utterances}
    assert "Speaker 2" in speakers  # renumbered, not silently merged into Speaker 1
