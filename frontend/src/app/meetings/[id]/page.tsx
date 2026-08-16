"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { StateChip } from "@/components/chip";
import { ProcessingView } from "@/components/processing-view";
import { Rail } from "@/components/rail";
import { Recap } from "@/components/recap";
import { ApiError, api, type MeetingDetail } from "@/lib/api/client";
import { formatDate, formatDuration } from "@/lib/format";
import { buildMarkdown } from "@/lib/markdown";
import { isActiveState } from "@/lib/states";
import { bumpRefresh, setBreadcrumb } from "@/lib/store";

export default function MeetingPage() {
  const params = useParams<{ id: string }>();
  const meetingId = params.id;
  const [detail, setDetail] = useState<MeetingDetail | null>(null);
  const [notFound, setNotFound] = useState(false);

  const refetch = useCallback(() => {
    api
      .getMeeting(meetingId)
      .then((d) => {
        setDetail(d);
        bumpRefresh();
      })
      .catch((error) => {
        if (error instanceof ApiError && error.status === 404) setNotFound(true);
      });
  }, [meetingId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useEffect(() => {
    if (!detail) return;
    const title = detail.summary?.title ?? detail.meeting.filename;
    setBreadcrumb(title);
    return () => setBreadcrumb("");
  }, [detail]);

  if (notFound) {
    return (
      <div className="py-16 text-center">
        <h1 className="font-semibold text-[20px] text-ink">Meeting not found</h1>
        <p className="mt-2 text-[13px] text-ink-muted">
          It may have been created against a different data directory.
        </p>
        <Link
          href="/"
          className="mt-4 inline-block font-medium text-[14px] text-violet transition-colors duration-120 hover:text-violet-deep"
        >
          Back to meetings
        </Link>
      </div>
    );
  }

  if (!detail) return null;

  const { meeting, summary } = detail;
  const active = isActiveState(meeting.state);
  const title = summary?.title ?? meeting.filename;

  const copyMarkdown = async () => {
    await navigator.clipboard.writeText(buildMarkdown(detail));
    toast.success("Markdown copied to clipboard");
  };

  return (
    <div>
      {/* Page header spans the full width ABOVE the column split — the record's
          title owns the page; both columns are its children. */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-semibold text-[20px] text-ink leading-[26px]">{title}</h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-ink-muted">
            <span>{formatDate(meeting.created_at)}</span>
            <span aria-hidden>·</span>
            <span>{formatDuration(meeting.duration_seconds)}</span>
            <span aria-hidden>·</span>
            <span>{meeting.language === "id" ? "Bahasa Indonesia" : "English"}</span>
            {summary && (
              <>
                <span aria-hidden>·</span>
                <span className="rounded-lg border border-hairline bg-sunken px-1.5 py-0.5 text-[12px]">
                  v{summary.version}
                </span>
              </>
            )}
            <StateChip state={meeting.state} />
          </p>
        </div>
        {summary && (
          <button
            type="button"
            onClick={copyMarkdown}
            className="h-8 shrink-0 rounded-lg border border-hairline px-3 font-medium text-[13px] text-ink-body transition-colors duration-120 hover:bg-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Copy Markdown
          </button>
        )}
      </header>

      {meeting.state === "failed" && (
        <div className="mt-5 rounded-xl border border-[#f0d4d1] bg-danger-wash px-4 py-3">
          <p className="font-medium text-[14px] text-[#b03a30]">Pipeline failed</p>
          <p className="mt-1 font-mono text-[12px] text-[#b03a30]/80 leading-4">
            {meeting.error ?? "Unknown error"}
          </p>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          {active ? (
            <ProcessingView
              meetingId={meeting.id}
              initialState={meeting.state}
              onSettled={refetch}
            />
          ) : summary ? (
            <Recap
              audioUrl={api.audioUrl(meeting.id)}
              summary={summary}
              transcript={detail.transcript}
            />
          ) : meeting.state !== "failed" ? (
            <p className="text-[13px] text-ink-muted">No summary available.</p>
          ) : null}
        </div>
        {!active && <Rail detail={detail} onChanged={refetch} />}
      </div>
    </div>
  );
}
