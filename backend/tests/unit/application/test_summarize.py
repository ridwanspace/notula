import json

import pytest

from notula.application.errors import SummarizationFailedError
from notula.application.ports import Completion
from notula.application.summarize import (
    build_user_prompt,
    summarize_transcript,
)
from notula.domain.models import SummaryLanguage, TokenUsage, Transcript, Utterance

VALID_JSON = json.dumps(
    {
        "title": "Weekly sync",
        "tldr": "Short recap.",
        "key_points": ["budget reviewed"],
        "decisions": [],
        "action_items": [{"task": "send the deck", "owner": None, "due": None}],
        "open_questions": [],
    }
)

TRANSCRIPT = Transcript(
    utterances=(Utterance(0.0, "Rina", "let's start with the budget"),),
    duration_seconds=30.0,
)


class ScriptedCompleter:
    """Returns pre-scripted outputs and records every prompt it receives."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.prompts: list[str] = []
        self.systems: list[str] = []

    @property
    def model(self) -> str:
        return "scripted-model"

    async def complete_json(self, system: str, user: str) -> Completion:
        self.systems.append(system)
        self.prompts.append(user)
        return Completion(
            text=self._outputs[len(self.prompts) - 1],
            usage=TokenUsage(10, 5),
            model=self.model,
        )


async def test_valid_first_attempt_needs_no_repair() -> None:
    completer = ScriptedCompleter([VALID_JSON])
    outcome = await summarize_transcript(completer, TRANSCRIPT, language=SummaryLanguage.ENGLISH)
    assert outcome.repair_attempts == 0
    assert outcome.usage == TokenUsage(10, 5)
    assert outcome.model == "scripted-model"
    assert outcome.summary.title == "Weekly sync"


async def test_invalid_then_valid_repairs_once_and_sums_usage() -> None:
    completer = ScriptedCompleter(["this is not json", VALID_JSON])
    outcome = await summarize_transcript(completer, TRANSCRIPT, language=SummaryLanguage.ENGLISH)
    assert outcome.repair_attempts == 1
    # The failed attempt still cost tokens.
    assert outcome.usage == TokenUsage(20, 10)
    repair_prompt = completer.prompts[1]
    assert "this is not json" in repair_prompt
    assert "not valid JSON" in repair_prompt
    assert "corrected JSON" in repair_prompt


async def test_exhausted_repairs_raise() -> None:
    completer = ScriptedCompleter(["nope", "still nope", "very much nope"])
    with pytest.raises(SummarizationFailedError, match="after 2 attempts"):
        await summarize_transcript(
            completer, TRANSCRIPT, language=SummaryLanguage.ENGLISH, max_repair_attempts=1
        )
    assert len(completer.prompts) == 2


async def test_transcript_text_reaches_the_prompt() -> None:
    completer = ScriptedCompleter([VALID_JSON])
    await summarize_transcript(completer, TRANSCRIPT, language=SummaryLanguage.ENGLISH)
    assert "let's start with the budget" in completer.prompts[0]
    assert "[00:00] Rina:" in completer.prompts[0]


def test_build_user_prompt_language_names() -> None:
    en = build_user_prompt("T", SummaryLanguage.ENGLISH, "")
    ind = build_user_prompt("T", SummaryLanguage.INDONESIAN, "")
    assert "English" in en
    assert "Bahasa Indonesia (formal register)" in ind


def test_build_user_prompt_roster_only_when_present() -> None:
    without = build_user_prompt("T", SummaryLanguage.ENGLISH, "   ")
    with_roster = build_user_prompt("T", SummaryLanguage.ENGLISH, "Rina, Dimas")
    assert "Known participants" not in without
    assert "Known participants: Rina, Dimas." in with_roster
