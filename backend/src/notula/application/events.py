"""Events the pipeline publishes while a meeting is processed.

Presentation serializes these to SSE. Events are ephemeral (in-memory bus);
durable progress lives in the meeting record and stage reports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    kind: str  # "state" | "progress" | "stage" | "completed" | "error"
    data: Mapping[str, object] = field(default_factory=dict)


def state_event(state: str) -> PipelineEvent:
    return PipelineEvent("state", {"state": state})


def progress_event(message: str, **extra: object) -> PipelineEvent:
    return PipelineEvent("progress", {"message": message, **extra})


def stage_event(
    stage: str, seconds: float, cost_usd: float | None, detail: str = ""
) -> PipelineEvent:
    return PipelineEvent(
        "stage", {"stage": stage, "seconds": seconds, "cost_usd": cost_usd, "detail": detail}
    )


def completed_event() -> PipelineEvent:
    return PipelineEvent("completed", {})


def error_event(message: str) -> PipelineEvent:
    return PipelineEvent("error", {"message": message})
