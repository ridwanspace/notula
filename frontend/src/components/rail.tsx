"use client";

import { useId, useState } from "react";
import { toast } from "sonner";
import { PipelineTable } from "@/components/pipeline-table";
import { ApiError, api, type MeetingDetail, type SummaryLanguage } from "@/lib/api/client";
import { formatDate, formatDuration } from "@/lib/format";

function RailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-hairline p-4">
      <h3 className="font-semibold text-[13px] text-ink">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ActionItems({ detail }: { detail: MeetingDetail }) {
  const summary = detail.summary;
  if (!summary) return null;
  return (
    <section className="rounded-xl border border-violet/25 bg-ai-panel p-4">
      <h3 className="font-semibold text-[13px] text-ink">Action items</h3>
      <p className="mt-1 font-medium text-[12px] text-violet-deep">
        ✦ AI-generated · {summary.model}
      </p>
      {summary.action_items.length === 0 ? (
        <p className="mt-3 text-[13px] text-ink-muted">No commitments were made.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {summary.action_items.map((item) => (
            <li key={item.task} className="flex gap-2.5">
              <input
                type="checkbox"
                aria-label={`Mark done: ${item.task}`}
                className="mt-0.5 size-4 shrink-0 rounded border-hairline accent-[#6f5ff8]"
              />
              <div className="min-w-0">
                <p className="text-[14px] text-ink-body leading-[18px]">{item.task}</p>
                <p className="mt-0.5 text-[12px] text-ink-muted">
                  {item.owner ?? "—"} · due {item.due ?? "—"}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Resummarize({ meetingId, onDone }: { meetingId: string; onDone: () => void }) {
  const selectId = useId();
  const [language, setLanguage] = useState<SummaryLanguage>("en");
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    try {
      const summary = await api.resummarize(meetingId, language);
      toast.success(`Summary v${summary.version} generated (${summary.language})`);
      onDone();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Re-summarize failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <RailCard title="Re-summarize">
      <p className="text-[12px] text-ink-muted leading-4">
        Runs pass 2 again from the stored transcript — no re-transcription.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <label htmlFor={selectId} className="sr-only">
          Summary language
        </label>
        <select
          id={selectId}
          value={language}
          onChange={(e) => setLanguage(e.target.value as SummaryLanguage)}
          className="h-8 flex-1 rounded-lg border border-hairline bg-canvas px-2 text-[13px] text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="en">English</option>
          <option value="id">Bahasa Indonesia</option>
        </select>
        <button
          type="button"
          disabled={running}
          onClick={run}
          className="h-8 rounded-lg border border-hairline px-3 font-medium text-[13px] text-ink-body transition-colors duration-120 hover:bg-sunken disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {running ? "Running…" : "Run"}
        </button>
      </div>
    </RailCard>
  );
}

export function Rail({ detail, onChanged }: { detail: MeetingDetail; onChanged: () => void }) {
  return (
    <div className="space-y-4">
      <ActionItems detail={detail} />
      {detail.stages.length > 0 && (
        <RailCard title="Pipeline — measured">
          <PipelineTable stages={detail.stages} />
        </RailCard>
      )}
      {detail.summary && <Resummarize meetingId={detail.meeting.id} onDone={onChanged} />}
      <RailCard title="Details">
        <dl className="space-y-2 text-[13px]">
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">File</dt>
            <dd className="truncate text-ink-body">{detail.meeting.filename}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">Created</dt>
            <dd className="text-ink-body">{formatDate(detail.meeting.created_at)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">Duration</dt>
            <dd className="text-ink-body">{formatDuration(detail.meeting.duration_seconds)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">Language</dt>
            <dd className="text-ink-body">
              {detail.meeting.language === "id" ? "Bahasa Indonesia" : "English"}
            </dd>
          </div>
        </dl>
      </RailCard>
    </div>
  );
}
