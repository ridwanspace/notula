import json

import pytest

from notula.domain.errors import SummaryParseError, TranscriptParseError
from notula.domain.models import SummaryLanguage
from notula.domain.parsing import (
    parse_timestamp,
    summary_from_dict,
    summary_from_json,
    summary_to_dict,
    transcript_from_dict,
    transcript_from_json,
    transcript_to_dict,
)

VALID_SUMMARY: dict[str, object] = {
    "title": "Weekly sync",
    "tldr": "Short recap.",
    "key_points": ["budget reviewed"],
    "decisions": ["ship on Friday"],
    "action_items": [
        {"task": "send the deck", "owner": "Rina", "due": None},
        {"task": "book the room", "owner": None, "due": "2026-08-20"},
    ],
    "open_questions": ["who owns QA?"],
}


class TestSummaryParsing:
    def test_happy_path(self) -> None:
        summary = summary_from_json(json.dumps(VALID_SUMMARY), language=SummaryLanguage.ENGLISH)
        assert summary.title == "Weekly sync"
        assert summary.action_items[0].owner == "Rina"
        assert summary.action_items[1].due == "2026-08-20"
        assert summary.language is SummaryLanguage.ENGLISH

    def test_code_fences_are_tolerated(self) -> None:
        text = f"```json\n{json.dumps(VALID_SUMMARY)}\n```"
        summary = summary_from_json(text, language=SummaryLanguage.ENGLISH)
        assert summary.tldr == "Short recap."

    def test_invalid_json_names_the_problem(self) -> None:
        with pytest.raises(SummaryParseError, match="not valid JSON"):
            summary_from_json("this is prose", language=SummaryLanguage.ENGLISH)

    def test_non_object_rejected(self) -> None:
        with pytest.raises(SummaryParseError, match="must be a JSON object"):
            summary_from_json("[1, 2]", language=SummaryLanguage.ENGLISH)

    def test_missing_title_named_in_error(self) -> None:
        data = {k: v for k, v in VALID_SUMMARY.items() if k != "title"}
        with pytest.raises(SummaryParseError, match="'title' must be a string"):
            summary_from_json(json.dumps(data), language=SummaryLanguage.ENGLISH)

    def test_wrong_element_type_names_the_index(self) -> None:
        data = dict(VALID_SUMMARY, key_points=["ok", 42])
        with pytest.raises(SummaryParseError, match=r"'key_points\[1\]' must be a string"):
            summary_from_json(json.dumps(data), language=SummaryLanguage.ENGLISH)

    def test_action_items_must_be_array(self) -> None:
        data = dict(VALID_SUMMARY, action_items="none")
        with pytest.raises(SummaryParseError, match="'action_items' must be an array"):
            summary_from_json(json.dumps(data), language=SummaryLanguage.ENGLISH)

    def test_action_item_must_be_object(self) -> None:
        data = dict(VALID_SUMMARY, action_items=["do it"])
        with pytest.raises(SummaryParseError, match=r"'action_items\[0\]' must be an object"):
            summary_from_json(json.dumps(data), language=SummaryLanguage.ENGLISH)

    def test_empty_task_rejected(self) -> None:
        data = dict(VALID_SUMMARY, action_items=[{"task": "  ", "owner": None, "due": None}])
        with pytest.raises(SummaryParseError, match=r"'action_items\[0\].task'"):
            summary_from_json(json.dumps(data), language=SummaryLanguage.ENGLISH)

    def test_owner_must_be_string_or_null(self) -> None:
        data = dict(VALID_SUMMARY, action_items=[{"task": "x", "owner": 7, "due": None}])
        with pytest.raises(SummaryParseError, match=r"'action_items\[0\].owner'"):
            summary_from_json(json.dumps(data), language=SummaryLanguage.ENGLISH)

    def test_round_trip(self) -> None:
        original = summary_from_json(json.dumps(VALID_SUMMARY), language=SummaryLanguage.INDONESIAN)
        restored = summary_from_dict(summary_to_dict(original))
        assert restored == original

    def test_from_dict_without_language_requires_language_field(self) -> None:
        with pytest.raises(SummaryParseError, match="'language'"):
            summary_from_dict(dict(VALID_SUMMARY))


class TestParseTimestamp:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("00:05", 5.0),
            ("05:30", 330.0),
            ("1:02:03", 3723.0),
            (45, 45.0),
            (12.5, 12.5),
            (0, 0.0),
        ],
    )
    def test_accepted_formats(self, value: object, expected: float) -> None:
        assert parse_timestamp(value, "utterances[0].start") == expected

    @pytest.mark.parametrize("value", ["75:00", "abc", "", None, True, -3])
    def test_rejected_values(self, value: object) -> None:
        with pytest.raises(TranscriptParseError, match=r"utterances\[0\].start"):
            parse_timestamp(value, "utterances[0].start")


class TestTranscriptParsing:
    def test_happy_path(self) -> None:
        text = json.dumps(
            {"utterances": [{"start": "00:05", "speaker": "Rina", "text": "selamat pagi"}]}
        )
        transcript = transcript_from_json(text, duration_seconds=60.0)
        assert transcript.utterances[0].start_seconds == 5.0
        assert transcript.duration_seconds == 60.0

    def test_missing_utterances_rejected(self) -> None:
        with pytest.raises(TranscriptParseError, match="'utterances' must be an array"):
            transcript_from_json("{}", duration_seconds=10.0)

    def test_blank_speaker_rejected(self) -> None:
        text = json.dumps({"utterances": [{"start": 0, "speaker": " ", "text": "hi"}]})
        with pytest.raises(TranscriptParseError, match=r"'utterances\[0\].speaker'"):
            transcript_from_json(text, duration_seconds=10.0)

    def test_missing_text_rejected(self) -> None:
        text = json.dumps({"utterances": [{"start": 0, "speaker": "A"}]})
        with pytest.raises(TranscriptParseError, match=r"'utterances\[0\].text'"):
            transcript_from_json(text, duration_seconds=10.0)

    def test_speaker_is_stripped(self) -> None:
        text = json.dumps({"utterances": [{"start": 0, "speaker": " Rina ", "text": "hi"}]})
        transcript = transcript_from_json(text, duration_seconds=10.0)
        assert transcript.utterances[0].speaker == "Rina"

    def test_round_trip(self) -> None:
        text = json.dumps(
            {
                "utterances": [
                    {"start": 5, "speaker": "A", "text": "one"},
                    {"start": 9.5, "speaker": "B", "text": "two"},
                ]
            }
        )
        original = transcript_from_json(text, duration_seconds=12.0)
        restored = transcript_from_dict(
            transcript_to_dict(original), duration_seconds=original.duration_seconds
        )
        assert restored == original


def test_transcript_utterance_must_be_object() -> None:
    with pytest.raises(TranscriptParseError, match=r"'utterances\[1\]' must be an object"):
        transcript_from_dict(
            {"utterances": [{"start": 0, "speaker": "A", "text": "hi"}, "not-an-object"]},
            duration_seconds=5.0,
        )
