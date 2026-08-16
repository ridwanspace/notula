# ADR 0004 — Deterministic offline mocks and the schema-repair loop

**Status:** accepted (2026-08-16)

## Context

Two separate problems share one design answer.

First, the repo must run — demo, tests, evals — with **zero API keys**, because
an evaluator who has to sign up for a key will not evaluate the project, and
because keyless tests are the only tests CI can honestly gate on.

Second, structured output is provider-uneven: Gemini enforces a response
schema server-side, but DeepSeek's OpenAI-compatible surface offers only
`json_object` mode, which guarantees JSON syntax — not the right JSON. The
wrong fields, a string where an array belongs, or a fenced code block are all
"valid JSON mode" outputs.

## Decision

**Offline mocks.** `NOTULA_PROVIDER=mock` (the default) swaps both providers
for deterministic fakes: the mock transcriber returns a bundled fixture when
the uploaded file's SHA-256 matches a known sample, and otherwise synthesizes
a transcript from a seeded RNG keyed by that hash — same file, same output,
forever. The mock summarizer derives its summary mechanically from the
transcript text. Any number produced under mock is **labelled mock** wherever
it appears; mock figures are never presented as real-model results.

**Schema repair.** Pass-2 output is validated by a strict stdlib parser whose
error messages name the exact offending field ("`action_items[2].task` must be
a non-empty string"). On failure, the raw output plus that error is fed back to
the model verbatim, up to 2 repair attempts, then the pipeline fails loudly —
no silent partial summaries. Repair attempts are counted and reported per
summary, so the rate is measurable instead of anecdotal.

**Capability fallbacks match parameters, not prose.** If a provider rejects
`response_format`, the fallback triggers only on a 4xx whose error names that
parameter — never on matching the vendor's error wording (it changes) and
never on a 5xx (an outage is not a missing capability).

## Consequences

- `git clone && make demo` works on a machine with no keys and no network
  access to any LLM provider; tests enforce this with a network guard.
- The repair loop is exercised in unit tests with a fake completer that
  returns malformed output first — no SDK, no network, fully deterministic.
- The mock summarizer is mechanical, so it cannot validate summary *quality*;
  that is what the live eval suite is for, and why mock and live results are
  reported in separate, labelled tables.
