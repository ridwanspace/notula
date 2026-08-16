"use client";

import { useRef } from "react";
import { ProvenancePanel } from "@/components/provenance-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Summary, TranscriptData } from "@/lib/api/client";
import { formatTimestamp } from "@/lib/format";

function HeadingBar({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="rounded-lg bg-white/70 px-3 py-1.5 font-semibold text-[13px] text-ink">
      {children}
    </h3>
  );
}

function ProseList({ items }: { items: string[] }) {
  return (
    <ul className="doc-prose mt-2 mb-4 list-disc space-y-1.5 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

/** Reading column: audio, then Summary | Transcript as a document. */
export function Recap({
  audioUrl,
  summary,
  transcript,
}: {
  audioUrl: string;
  summary: Summary;
  transcript: TranscriptData | null;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);

  const seek = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = seconds;
    void audio.play();
  };

  return (
    <div>
      <div className="rounded-xl border border-hairline bg-sunken p-4">
        {/* biome-ignore lint/a11y/useMediaCaption: transcript with timestamps is rendered below the player */}
        <audio ref={audioRef} controls preload="metadata" src={audioUrl} className="w-full" />
        <p className="mt-2 text-center text-[12px] text-ink-muted">
          Click any transcript timestamp to jump the audio there.
        </p>
      </div>

      <Tabs defaultValue="summary" className="mt-6">
        <TabsList className="h-auto w-full justify-start gap-6 rounded-none border-hairline border-b bg-transparent p-0">
          {["summary", "transcript"].map((tab) => (
            <TabsTrigger
              key={tab}
              value={tab}
              className="-mb-px rounded-none border-0 border-b-2 border-b-transparent bg-transparent px-0 pb-2 font-medium text-[14px] text-ink-muted capitalize shadow-none transition-colors duration-120 data-[state=active]:border-b-violet data-[state=active]:bg-transparent data-[state=active]:text-violet data-[state=active]:shadow-none"
            >
              {tab}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="summary" className="mt-5">
          <ProvenancePanel model={summary.model} repairAttempts={summary.repair_attempts}>
            <HeadingBar>TL;DR</HeadingBar>
            <p className="doc-prose mt-2 mb-4">{summary.tldr}</p>
            {summary.key_points.length > 0 && (
              <>
                <HeadingBar>Key points</HeadingBar>
                <ProseList items={summary.key_points} />
              </>
            )}
            <HeadingBar>Decisions</HeadingBar>
            {summary.decisions.length > 0 ? (
              <ProseList items={summary.decisions} />
            ) : (
              <p className="doc-prose mt-2 mb-4 text-ink-muted">
                Nothing was decided in this meeting.
              </p>
            )}
            {summary.open_questions.length > 0 && (
              <>
                <HeadingBar>Open questions</HeadingBar>
                <ProseList items={summary.open_questions} />
              </>
            )}
          </ProvenancePanel>
        </TabsContent>

        <TabsContent value="transcript" className="mt-5">
          {transcript && transcript.utterances.length > 0 ? (
            <ul className="space-y-3">
              {transcript.utterances.map((u) => (
                <li
                  key={`${u.start}-${u.speaker}-${u.text.slice(0, 24)}`}
                  className="grid grid-cols-[56px_minmax(0,1fr)] gap-3"
                >
                  <button
                    type="button"
                    onClick={() => seek(u.start)}
                    className="h-fit rounded font-mono text-[12px] text-violet tabular-nums transition-colors duration-120 hover:text-violet-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {formatTimestamp(u.start)}
                  </button>
                  <p className="doc-prose">
                    <span className="font-medium text-ink">{u.speaker}</span> <span>{u.text}</span>
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-ink-muted">No transcript stored for this meeting.</p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
