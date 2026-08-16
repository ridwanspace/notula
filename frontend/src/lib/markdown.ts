import type { MeetingDetail } from "@/lib/api/client";
import { formatDuration, formatTimestamp } from "@/lib/format";

/** Render a completed meeting as portable Markdown for the copy-export action. */
export function buildMarkdown(detail: MeetingDetail): string {
  const { meeting, summary } = detail;
  if (!summary) return `# ${meeting.filename}\n\n_No summary yet._\n`;

  const lines: string[] = [
    `# ${summary.title}`,
    "",
    `_${meeting.filename} · ${formatDuration(meeting.duration_seconds)} · summary v${summary.version} (${summary.model})_`,
    "",
    "## TL;DR",
    "",
    summary.tldr,
  ];

  const section = (heading: string, items: string[]) => {
    if (items.length === 0) return;
    lines.push("", `## ${heading}`, "");
    for (const item of items) lines.push(`- ${item}`);
  };

  section("Key points", summary.key_points);
  section("Decisions", summary.decisions);

  if (summary.action_items.length > 0) {
    lines.push("", "## Action items", "");
    for (const item of summary.action_items) {
      const owner = item.owner ?? "—";
      const due = item.due ? `, due ${item.due}` : "";
      lines.push(`- [ ] ${item.task} _(${owner}${due})_`);
    }
  }

  section("Open questions", summary.open_questions);

  if (detail.transcript && detail.transcript.utterances.length > 0) {
    lines.push("", "## Transcript", "");
    for (const u of detail.transcript.utterances) {
      lines.push(`**[${formatTimestamp(u.start)}] ${u.speaker}:** ${u.text}`);
      lines.push("");
    }
  }

  return `${lines.join("\n").trimEnd()}\n`;
}
