# ADR 0001 — Layered architecture with CI-enforced import contracts

**Status:** accepted (2026-08-16)

## Context

The pipeline touches two vendor SDKs (Gemini for audio transcription, an
OpenAI-compatible client for DeepSeek summarization), a database, ffmpeg, and a
web framework. The parts most worth testing — the meeting state machine, chunk
planning and merging, cost arithmetic, the schema-repair loop — have nothing to
do with any of those. If SDK types leak into that logic, every provider change
ripples through the codebase and every test needs a stub of a vendor client.

## Decision

Three layers, dependencies pointing inward, enforced by import-linter in CI
(`make arch`), not by convention:

```
presentation | infrastructure   (FastAPI, SQLAlchemy, ffmpeg, vendor SDKs)
        -> application          (use cases + ports; stdlib only)
        -> domain               (models, state machine, chunking, costing, parsing)
```

- **domain** is stdlib-only: plain dataclasses, no Pydantic, no framework.
  A `forbidden` contract lists every framework and SDK by name.
- **application** defines `Protocol` ports (`Transcriber`, `ChatCompleter`,
  `MeetingRepository`, `AudioProcessor`, `EventBus`) and orchestrates through
  them. Same stdlib-only restriction.
- **infrastructure** implements the ports. Vendor SDKs (`openai`, `google`) are
  further quarantined into `infrastructure/providers` by a dedicated contract.
- **presentation** is FastAPI routes + Pydantic schemas at the edge; the
  composition root (`notula/main.py`) sits outside the layers and wires
  everything together.

## Consequences

- Pass-2 summarization is swappable per provider by implementing one port; the
  repair loop is tested with a fake completer and no SDK import anywhere.
- The domain + application core carries a 100% unit-coverage gate in CI, which
  is only realistic because those layers have no I/O to mock.
- Cost: some ceremony (port definitions, record dataclasses at the boundary)
  for a codebase this size. Accepted — the contracts are the point, and a
  violated contract fails CI on unchanged tests.
