"""Strict validation of LLM JSON output into domain models, plus round-trip
serialization for storage.

Error messages name the exact offending field ("action_items[2].task must be a
string") because the repair loop feeds them back to the model verbatim — vague
messages produce vague repairs.
"""

from __future__ import annotations

import json
import re

from notula.domain.errors import SummaryParseError, TranscriptParseError
from notula.domain.models import (
    ActionItem,
    MeetingSummary,
    SummaryLanguage,
    Transcript,
    Utterance,
)

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9]*\s*|\s*```\s*$")
_TIMESTAMP = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]\d)$")


def _strip_fences(text: str) -> str:
    return _FENCE.sub("", text)


def _load_object(text: str, error: type[Exception]) -> dict[str, object]:
    try:
        data: object = json.loads(_strip_fences(text))
    except json.JSONDecodeError as e:
        raise error(f"output is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise error(f"output must be a JSON object, got {type(data).__name__}")
    return data


def _string(data: dict[str, object], key: str, error: type[Exception]) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise error(f"'{key}' must be a string, got {type(value).__name__}")
    return value


def _string_list(data: dict[str, object], key: str, error: type[Exception]) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list):
        raise error(f"'{key}' must be an array of strings, got {type(value).__name__}")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise error(f"'{key}[{i}]' must be a string, got {type(item).__name__}")
        out.append(item)
    return tuple(out)


def _optional_string(value: object, path: str, error: type[Exception]) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise error(f"'{path}' must be a string or null, got {type(value).__name__}")


def parse_timestamp(value: object, path: str) -> float:
    """Accept ``MM:SS`` / ``H:MM:SS`` strings or plain seconds."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value < 0:
            raise TranscriptParseError(f"'{path}' must be >= 0, got {value}")
        return float(value)
    if isinstance(value, str):
        match = _TIMESTAMP.match(value.strip())
        if match:
            hours = int(match.group(1) or 0)
            return hours * 3600 + int(match.group(2)) * 60 + int(match.group(3))
    raise TranscriptParseError(f"'{path}' must be 'MM:SS', 'H:MM:SS' or seconds, got {value!r}")


def summary_from_dict(
    data: dict[str, object], *, language: SummaryLanguage | None = None
) -> MeetingSummary:
    if language is None:
        raw = data.get("language")
        if not isinstance(raw, str):
            raise SummaryParseError("'language' must be a string when not supplied externally")
        language = SummaryLanguage(raw)

    raw_items = data.get("action_items")
    if not isinstance(raw_items, list):
        raise SummaryParseError(f"'action_items' must be an array, got {type(raw_items).__name__}")
    items: list[ActionItem] = []
    for i, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise SummaryParseError(f"'action_items[{i}]' must be an object")
        task = raw_item.get("task")
        if not isinstance(task, str) or not task.strip():
            raise SummaryParseError(f"'action_items[{i}].task' must be a non-empty string")
        items.append(
            ActionItem(
                task=task,
                owner=_optional_string(
                    raw_item.get("owner"), f"action_items[{i}].owner", SummaryParseError
                ),
                due=_optional_string(
                    raw_item.get("due"), f"action_items[{i}].due", SummaryParseError
                ),
            )
        )

    return MeetingSummary(
        title=_string(data, "title", SummaryParseError),
        tldr=_string(data, "tldr", SummaryParseError),
        key_points=_string_list(data, "key_points", SummaryParseError),
        decisions=_string_list(data, "decisions", SummaryParseError),
        action_items=tuple(items),
        open_questions=_string_list(data, "open_questions", SummaryParseError),
        language=language,
    )


def summary_from_json(text: str, *, language: SummaryLanguage) -> MeetingSummary:
    return summary_from_dict(_load_object(text, SummaryParseError), language=language)


def summary_to_dict(summary: MeetingSummary) -> dict[str, object]:
    return {
        "title": summary.title,
        "tldr": summary.tldr,
        "key_points": list(summary.key_points),
        "decisions": list(summary.decisions),
        "action_items": [
            {"task": a.task, "owner": a.owner, "due": a.due} for a in summary.action_items
        ],
        "open_questions": list(summary.open_questions),
        "language": summary.language.value,
    }


def transcript_from_dict(data: dict[str, object], *, duration_seconds: float) -> Transcript:
    raw = data.get("utterances")
    if not isinstance(raw, list):
        raise TranscriptParseError(f"'utterances' must be an array, got {type(raw).__name__}")
    utterances: list[Utterance] = []
    for i, raw_u in enumerate(raw):
        if not isinstance(raw_u, dict):
            raise TranscriptParseError(f"'utterances[{i}]' must be an object")
        speaker = raw_u.get("speaker")
        text = raw_u.get("text")
        if not isinstance(speaker, str) or not speaker.strip():
            raise TranscriptParseError(f"'utterances[{i}].speaker' must be a non-empty string")
        if not isinstance(text, str):
            raise TranscriptParseError(f"'utterances[{i}].text' must be a string")
        utterances.append(
            Utterance(
                start_seconds=parse_timestamp(raw_u.get("start"), f"utterances[{i}].start"),
                speaker=speaker.strip(),
                text=text,
            )
        )
    return Transcript(utterances=tuple(utterances), duration_seconds=duration_seconds)


def transcript_from_json(text: str, *, duration_seconds: float) -> Transcript:
    return transcript_from_dict(
        _load_object(text, TranscriptParseError), duration_seconds=duration_seconds
    )


def transcript_to_dict(transcript: Transcript) -> dict[str, object]:
    return {
        "duration_seconds": transcript.duration_seconds,
        "utterances": [
            {"start": u.start_seconds, "speaker": u.speaker, "text": u.text}
            for u in transcript.utterances
        ],
    }
