"""Pass-2 summarization with a schema-repair loop.

The completer returns raw text; validation lives here. DeepSeek's json_object
mode does not accept a schema parameter, so the expected shape is described in
the prompt and enforced by ``notula.domain.parsing`` — when validation fails,
the exact error is fed back to the model for a corrected attempt.
"""

from __future__ import annotations

from dataclasses import dataclass

from notula.application.errors import SummarizationFailedError
from notula.application.ports import ChatCompleter
from notula.domain.errors import SummaryParseError
from notula.domain.models import MeetingSummary, SummaryLanguage, TokenUsage, Transcript
from notula.domain.parsing import summary_from_json

SYSTEM_PROMPT = """You are a precise meeting analyst. You turn a diarized meeting
transcript into a structured summary.

Respond with a single JSON object and nothing else — no prose, no code fences.
The object must have exactly these fields:
- "title": string — a short descriptive title based on the meeting content.
- "tldr": string — a 2-3 sentence summary.
- "key_points": array of strings.
- "decisions": array of strings. A decision requires something actually being
  decided in the transcript; if nothing was decided, use an empty array.
- "action_items": array of objects, each {"task": string, "owner": string or null,
  "due": string or null}. An action item requires a commitment or clear
  assignment. Never invent owners or due dates — use null when not stated.
- "open_questions": array of strings.

Rules:
- Keep quoted phrases, names, and technical terms exactly as they appear in the
  transcript.
- Passages marked [inaudible] stay [inaudible]; never guess at them.
- Base every field only on what the transcript actually says."""

_LANGUAGE_NAMES: dict[SummaryLanguage, str] = {
    SummaryLanguage.ENGLISH: "English",
    SummaryLanguage.INDONESIAN: "Bahasa Indonesia (formal register)",
}

_ROSTER_RULE = """
Known participants: {roster}.
Spell these names EXACTLY as given above, both when referring to people and in
action-item owners. If a speaker cannot be confidently mapped to a participant,
keep the transcript's speaker label."""


@dataclass(frozen=True, slots=True)
class SummarizeOutcome:
    summary: MeetingSummary
    usage: TokenUsage
    repair_attempts: int
    model: str


def build_user_prompt(transcript_text: str, language: SummaryLanguage, roster: str) -> str:
    prompt = f"Write ALL summary fields in {_LANGUAGE_NAMES[language]}."
    if roster.strip():
        prompt += _ROSTER_RULE.format(roster=roster.strip())
    prompt += f"\n\nTranscript:\n{transcript_text}"
    return prompt


def _repair_prompt(base: str, previous_output: str, error: str) -> str:
    return (
        f"{base}\n\n"
        "Your previous response failed schema validation.\n"
        f"Previous response:\n{previous_output}\n\n"
        f"Validation error: {error}\n"
        "Return the corrected JSON object only."
    )


async def summarize_transcript(
    completer: ChatCompleter,
    transcript: Transcript,
    *,
    language: SummaryLanguage,
    roster: str = "",
    max_repair_attempts: int = 2,
) -> SummarizeOutcome:
    """Summarize a transcript, repairing schema-invalid output up to
    ``max_repair_attempts`` times. Usage is summed across every attempt —
    a repaired call still costs the failed attempts."""
    base_prompt = build_user_prompt(transcript.as_text(), language, roster)
    usage_total = TokenUsage()
    prompt = base_prompt
    last_error = ""
    for attempt in range(1 + max_repair_attempts):
        completion = await completer.complete_json(SYSTEM_PROMPT, prompt)
        usage_total = usage_total + completion.usage
        try:
            summary = summary_from_json(completion.text, language=language)
        except SummaryParseError as e:
            last_error = str(e)
            prompt = _repair_prompt(base_prompt, completion.text, last_error)
            continue
        return SummarizeOutcome(
            summary=summary,
            usage=usage_total,
            repair_attempts=attempt,
            model=completion.model,
        )
    raise SummarizationFailedError(
        f"summarizer output failed validation after {1 + max_repair_attempts} attempts: "
        f"{last_error}"
    )
