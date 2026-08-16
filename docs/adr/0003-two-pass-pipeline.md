# ADR 0003 — Two-pass pipeline: the transcript is the system of record

**Status:** accepted (2026-08-16)

## Context

The MVP this project grew from did everything in one multimodal call: audio in,
diarized transcript + summary out. Simple, but it couples the cheap part to the
expensive part: changing the summary language, fixing a prompt bug, or trying a
different summarizer meant paying for (and waiting on) transcription again.

Audio is the expensive input. Gemini's docs quote ~32 tokens per second of
audio (<https://ai.google.dev/gemini-api/docs/audio>) — an input-side *estimate*
(60 minutes ≈ 115,200 tokens ≈ $0.17 at the published $1.50/1M input rate,
prices as of 2026-08-16, <https://ai.google.dev/gemini-api/docs/pricing>).
A measured run of a real 60-second clip billed 1,617 prompt tokens (audio +
instruction text — *below* the naive 1,920) plus 245 output tokens, $0.0046
total; output tokens for the transcript JSON roughly double the input-only
figure. This is why the cost meter always bills from the provider's reported
usage metadata and treats the 32-tok/s figure as a planning estimate only.
The same audio re-summarized from transcript text is a few hundred text tokens
on DeepSeek v4-flash ($0.14/1M in, $0.28/1M out — <https://deepseek.ai/pricing>):
a fraction of a cent, measured $0.0003 per summary on the same clip.

## Decision

- **Pass 1 (audio → transcript):** Gemini multimodal, once per meeting. The
  diarized, timestamped transcript is persisted and becomes the system of
  record.
- **Pass 2 (transcript → summary):** runs from stored transcript *text* on the
  cheapest capable model (DeepSeek v4-flash by default), through the
  schema-repair loop (ADR 0004). Summaries are versioned.
- **Re-runnable by design:** the state machine allows
  `COMPLETED → SUMMARIZING → COMPLETED`, so a language switch (EN ⇄ formal
  Bahasa Indonesia) or a prompt upgrade regenerates the summary without
  re-transcribing. A failed re-run reverts to `COMPLETED` and keeps the last
  good summary — a bad prompt experiment can't destroy a meeting.

## Consequences

- Pass-2 experimentation is effectively free, which is what makes an eval
  suite over summaries practical (see `evals/`).
- The transcript schema is now a contract; transcription-quality issues are
  visible (and measurable) instead of being blended into summary quality.
- Two calls instead of one adds latency for the first summary. Accepted: the
  pipeline is asynchronous and the per-stage timings are reported per meeting.
