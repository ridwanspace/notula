"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { formatCost, formatSeconds } from "@/lib/format";
import { cn } from "@/lib/utils";

const STAGES = ["normalize", "transcribe", "summarize"] as const;

const STATE_TO_STAGE: Record<string, number> = {
  uploaded: -1,
  normalizing: 0,
  transcribing: 1,
  summarizing: 2,
};

interface LogLine {
  at: number;
  text: string;
}

/** Live pipeline progress over SSE; calls onSettled when the stream ends. */
export function ProcessingView({
  meetingId,
  initialState,
  onSettled,
}: {
  meetingId: string;
  initialState: string;
  onSettled: () => void;
}) {
  const [state, setState] = useState(initialState);
  const [log, setLog] = useState<LogLine[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(Date.now());
  const settled = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((Date.now() - started.current) / 1000), 100);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const push = (text: string) =>
      setLog((prev) => [...prev, { at: (Date.now() - started.current) / 1000, text }]);
    const settle = () => {
      if (!settled.current) {
        settled.current = true;
        onSettled();
      }
    };

    const source = new EventSource(api.eventsUrl(meetingId));
    source.addEventListener("state", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as { state: string };
      setState(data.state);
    });
    source.addEventListener("progress", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as { message: string };
      push(data.message);
    });
    source.addEventListener("stage", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as {
        stage: string;
        seconds: number;
        cost_usd: number | null;
      };
      push(`${data.stage} done in ${formatSeconds(data.seconds)} · ${formatCost(data.cost_usd)}`);
    });
    source.addEventListener("completed", () => {
      source.close();
      settle();
    });
    source.addEventListener("error", (e) => {
      // A named pipeline "error" event carries data; the EventSource network
      // error callback does not — on a network drop, fall back to a refetch.
      if (e instanceof MessageEvent && e.data) {
        const data = JSON.parse(e.data) as { message: string };
        push(`error: ${data.message}`);
      }
      source.close();
      settle();
    });
    return () => source.close();
  }, [meetingId, onSettled]);

  const activeIndex = STATE_TO_STAGE[state] ?? -1;

  return (
    <div className="rounded-xl border border-hairline p-6">
      <div className="flex items-center justify-between">
        <ol className="flex items-center gap-2">
          {STAGES.map((stage, i) => (
            <li key={stage} className="flex items-center gap-2">
              {i > 0 && <span className="h-px w-6 bg-hairline" />}
              <span
                className={cn(
                  "rounded-lg px-2.5 py-1 font-medium text-[13px]",
                  i < activeIndex && "text-ink",
                  i === activeIndex && "bg-ai-wash text-violet-deep",
                  i > activeIndex && "text-ink-faint",
                )}
              >
                {i < activeIndex ? `${stage} ✓` : stage}
              </span>
            </li>
          ))}
        </ol>
        <span className="font-mono text-[12px] text-ink-muted tabular-nums">
          {elapsed.toFixed(1)}s
        </span>
      </div>

      <ul className="mt-5 space-y-1 border-hairline border-t pt-4 font-mono text-[12px] text-ink-muted">
        {log.length === 0 && <li>waiting for pipeline events…</li>}
        {log.map((line) => (
          <li key={`${line.at}-${line.text}`}>
            <span className="tabular-nums">[{line.at.toFixed(1)}s]</span> {line.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
