import { describe, expect, it } from "vitest";
import type { MeetingDetail } from "@/lib/api/client";
import { buildMarkdown } from "@/lib/markdown";

const detail: MeetingDetail = {
  meeting: {
    id: "m1",
    filename: "standup.wav",
    state: "completed",
    language: "en",
    duration_seconds: 60,
    created_at: "2026-08-16T09:00:00+00:00",
    error: null,
  },
  stages: [],
  transcript: {
    duration_seconds: 60,
    utterances: [{ start: 2, speaker: "Rina", text: "Morning semua." }],
  },
  summary: {
    title: "Weekly standup",
    tldr: "Short sync.",
    key_points: ["Point one"],
    decisions: [],
    action_items: [
      { task: "Fix the CSV bug", owner: "Dimas", due: "Friday" },
      { task: "Prepare staging", owner: null, due: null },
    ],
    open_questions: ["Feature flag needed?"],
    language: "en",
    model: "mock",
    version: 2,
    repair_attempts: 0,
    created_at: "2026-08-16T09:01:00+00:00",
  },
};

describe("buildMarkdown", () => {
  const md = buildMarkdown(detail);

  it("leads with the summary title and meta", () => {
    expect(md.startsWith("# Weekly standup\n")).toBe(true);
    expect(md).toContain("summary v2 (mock)");
  });

  it("omits empty sections entirely", () => {
    expect(md).not.toContain("## Decisions");
    expect(md).toContain("## Key points");
  });

  it("renders action items as checkboxes with owner and null-safe due", () => {
    expect(md).toContain("- [ ] Fix the CSV bug _(Dimas, due Friday)_");
    expect(md).toContain("- [ ] Prepare staging _(—)_");
  });

  it("includes the timestamped transcript", () => {
    expect(md).toContain("**[00:02] Rina:** Morning semua.");
  });
});
