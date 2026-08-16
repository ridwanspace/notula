"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StateChip } from "@/components/chip";
import { api, type Meeting } from "@/lib/api/client";
import { formatDate, formatDuration } from "@/lib/format";
import { useRefreshTick } from "@/lib/store";

export function MeetingList() {
  const tick = useRefreshTick();
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void tick; // refresh signal: refetch after mutations elsewhere
    let cancelled = false;
    api
      .listMeetings()
      .then((r) => {
        if (!cancelled) setMeetings(r.meetings);
      })
      .catch(() => {
        if (!cancelled) setError("Could not reach the backend — is it running on :8000?");
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  if (error) return <p className="text-[13px] text-ink-muted">{error}</p>;
  if (meetings === null) return null;
  if (meetings.length === 0) {
    return (
      <p className="text-[13px] text-ink-muted">
        No meetings yet — drop a recording above to get your first recap.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-hairline rounded-xl border border-hairline">
      {meetings.map((m) => (
        <li key={m.id}>
          <Link
            href={`/meetings/${m.id}`}
            className="flex h-12 items-center gap-4 px-4 transition-colors duration-120 hover:bg-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="min-w-0 flex-1 truncate font-medium text-[14px] text-ink">
              {m.filename}
            </span>
            <span className="shrink-0 text-[12px] text-ink-muted">
              {formatDate(m.created_at)} · {formatDuration(m.duration_seconds)}
            </span>
            <StateChip state={m.state} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
