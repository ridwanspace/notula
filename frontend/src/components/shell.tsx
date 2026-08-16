"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Health, type Meeting } from "@/lib/api/client";
import { isActiveState } from "@/lib/states";
import { useBreadcrumb, useRefreshTick } from "@/lib/store";
import { cn } from "@/lib/utils";

function StateDot({ state }: { state: string }) {
  if (state === "failed") return <span className="size-1.5 rounded-full bg-danger" />;
  if (isActiveState(state))
    return <span className="size-1.5 animate-pulse rounded-full bg-violet" />;
  return null;
}

function RecentMeetings() {
  const pathname = usePathname();
  const tick = useRefreshTick();
  const [meetings, setMeetings] = useState<Meeting[]>([]);

  useEffect(() => {
    void tick; // refresh signal
    void pathname; // refetch on navigation
    let cancelled = false;
    api
      .listMeetings()
      .then((r) => {
        if (!cancelled) setMeetings(r.meetings.slice(0, 8));
      })
      .catch(() => {
        // Sidebar list is best-effort; the page surfaces real errors.
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, tick]);

  if (meetings.length === 0) return null;
  return (
    <div className="mt-6 min-h-0 flex-1 overflow-y-auto">
      <p className="px-3 font-medium text-[12px] text-ink-muted uppercase tracking-wide">Recent</p>
      <ul className="mt-2 space-y-0.5 px-1">
        {meetings.map((m) => {
          const href = `/meetings/${m.id}`;
          const active = pathname === href;
          return (
            <li key={m.id}>
              <Link
                href={href}
                className={cn(
                  "flex h-9 items-center gap-2 rounded-lg border border-transparent px-2 text-[13px] text-ink-muted transition-colors duration-120 hover:text-ink",
                  active && "border-hairline bg-canvas text-ink",
                )}
              >
                <span className="truncate">{m.filename}</span>
                <span className="ml-auto shrink-0">
                  <StateDot state={m.state} />
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ProviderCard() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);
  return (
    <div className="rounded-xl border border-hairline bg-canvas p-3">
      <p className="text-[12px] text-ink-muted">Provider</p>
      <p className="mt-0.5 font-medium text-[13px] text-ink">
        {health ? health.provider : "unreachable"}
      </p>
      <p className="mt-0.5 text-[12px] text-ink-muted leading-4">
        {health?.provider === "mock"
          ? "Deterministic demo output — no API keys."
          : health?.provider === "live"
            ? "Gemini + DeepSeek."
            : "Start the backend on :8000."}
      </p>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const breadcrumb = useBreadcrumb();
  const pathname = usePathname();

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-64 flex-col border-hairline border-r bg-sunken">
        <div className="flex h-14 items-center gap-2.5 px-4">
          <span className="flex size-6 items-center justify-center rounded-lg bg-violet text-[13px] text-white">
            ✦
          </span>
          <span className="font-semibold text-[14px] text-ink">Notula</span>
        </div>
        <div className="px-3">
          <Link
            href="/"
            className="flex h-8 items-center justify-center rounded-lg bg-violet font-medium text-[14px] text-white transition-colors duration-120 hover:bg-violet-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            New meeting
          </Link>
        </div>
        <nav className="mt-4 px-1">
          <Link
            href="/"
            className={cn(
              "flex h-9 items-center gap-2 rounded-lg border border-transparent px-2 font-medium text-[14px] text-ink-faint transition-colors duration-120 hover:text-ink",
              pathname === "/" && "border-hairline bg-canvas text-ink",
            )}
          >
            Meetings
          </Link>
        </nav>
        <RecentMeetings />
        <div className="space-y-3 p-3">
          <ProviderCard />
          <a
            href="https://github.com/ridwanspace/notula"
            target="_blank"
            rel="noreferrer"
            className="block px-1 text-[12px] text-ink-muted transition-colors duration-120 hover:text-ink"
          >
            github.com/ridwanspace/notula
          </a>
        </div>
      </aside>

      <div className="pl-64">
        <header className="flex h-14 items-center border-hairline border-b px-8">
          <nav aria-label="Breadcrumb" className="text-[13px] text-ink-muted">
            <Link href="/" className="transition-colors duration-120 hover:text-ink">
              Meetings
            </Link>
            {breadcrumb && (
              <>
                <span className="mx-2 text-ink-faint">/</span>
                <span className="text-ink">{breadcrumb}</span>
              </>
            )}
          </nav>
        </header>
        <main className="mx-auto max-w-[1024px] px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
