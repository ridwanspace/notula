"use client";

import { useEffect } from "react";
import { MeetingList } from "@/components/meeting-list";
import { UploadCard } from "@/components/upload-card";
import { setBreadcrumb } from "@/lib/store";

export default function HomePage() {
  useEffect(() => {
    setBreadcrumb("");
  }, []);

  return (
    <div>
      <header>
        <h1 className="font-semibold text-[20px] text-ink leading-[26px]">New meeting</h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          Upload a recording — the transcript becomes the system of record, and summaries are
          re-runnable from it.
        </p>
      </header>
      <div className="mt-5">
        <UploadCard />
      </div>
      <section className="mt-10">
        <h2 className="font-semibold text-[16px] text-ink">Meetings</h2>
        <div className="mt-3">
          <MeetingList />
        </div>
      </section>
    </div>
  );
}
