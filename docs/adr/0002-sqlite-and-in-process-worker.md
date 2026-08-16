# ADR 0002 — SQLite + in-process asyncio worker (no Postgres, no Redis)

**Status:** accepted (2026-08-16)

## Context

The pipeline is asynchronous: an upload returns immediately and a worker drives
the meeting through `uploaded → normalizing → transcribing → summarizing →
completed/failed`. The obvious production shape is Postgres + a Redis-backed
queue (arq/RQ). But this repository's acceptance test is:

```
git clone && make demo
```

with zero infrastructure and zero API keys. A recruiter will not start Docker,
and a queue server here would prove nothing that is verifiable offline.

## Decision

- **SQLite via aiosqlite + SQLAlchemy 2 async** as the system of record
  (meetings, transcripts, summaries, per-stage reports).
- **One in-process asyncio worker** consuming an `asyncio.Queue`.
- **Startup recovery:** on boot the worker re-enqueues every meeting left in a
  non-terminal state, so a crash mid-pipeline resumes instead of stranding
  jobs. This is the durability property that actually matters, and it is
  integration-tested.
- **`create_all` instead of Alembic migrations** while the schema is young.
  Migrations get added when the first breaking schema change lands, not
  before there is anything to migrate.

## Consequences

- Single process, no horizontal scaling, one writer. Fine for the intended
  scale (a demo and a self-hosted single-team instance).
- At production scale the seams are already in place: `MeetingRepository` is a
  port, so Postgres is a new adapter; the worker consumes a queue interface
  that maps directly onto arq. Redis-backed budget/queue engineering is
  demonstrated separately in the author's `llm-cost-gateway` repository —
  duplicating it here would add infrastructure without adding evidence.
- Every test and the demo run with no services, which is what keeps the CI
  honest (no secrets referenced anywhere in the workflows).
