"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiError, api, type SummaryLanguage } from "@/lib/api/client";
import { formatBytes } from "@/lib/format";
import { bumpRefresh } from "@/lib/store";
import { cn } from "@/lib/utils";

const LANGUAGE_KEY = "notula.language";

export function UploadCard() {
  const router = useRouter();
  const inputId = useId();
  const rosterId = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [roster, setRoster] = useState("");
  const [language, setLanguage] = useState<SummaryLanguage>("en");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(LANGUAGE_KEY);
    if (saved === "en" || saved === "id") setLanguage(saved);
  }, []);

  const pickLanguage = (next: SummaryLanguage) => {
    setLanguage(next);
    window.localStorage.setItem(LANGUAGE_KEY, next);
  };

  const submit = async () => {
    if (!file || submitting) return;
    setSubmitting(true);
    try {
      const { id } = await api.submitMeeting(file, roster.trim(), language);
      bumpRefresh();
      router.push(`/meetings/${id}`);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Upload failed — is the backend running?",
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-hairline">
      {/* biome-ignore lint/a11y/noStaticElementInteractions: drag-and-drop enhances the keyboard-accessible file input below */}
      {/* biome-ignore lint/a11y/noNoninteractiveElementInteractions: same — the input remains the accessible path */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const dropped = e.dataTransfer.files[0];
          if (dropped) setFile(dropped);
        }}
        className={cn(
          "m-2 rounded-lg border border-hairline border-dashed px-6 py-12 text-center transition-colors duration-120",
          dragging && "border-violet bg-ai-wash",
        )}
      >
        <label htmlFor={inputId} className="cursor-pointer">
          <span className="font-medium text-[14px] text-ink">Drop a recording here</span>{" "}
          <span className="text-[14px] text-ink-muted">or click to browse</span>
          <span className="mt-1 block text-[12px] text-ink-muted">
            MP3 · WAV · FLAC · M4A · OGG — long recordings are chunked automatically
          </span>
        </label>
        <input
          ref={fileInput}
          id={inputId}
          type="file"
          accept="audio/*,.m4a,.flac"
          className="sr-only"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {file && (
        <div className="flex items-center justify-between gap-3 border-hairline border-t px-4 py-3">
          <div className="min-w-0">
            <p className="truncate font-medium text-[14px] text-ink">{file.name}</p>
            <p className="text-[12px] text-ink-muted">{formatBytes(file.size)}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setFile(null);
              if (fileInput.current) fileInput.current.value = "";
            }}
            className="rounded-lg border border-hairline px-3 py-1.5 text-[13px] text-ink-body transition-colors duration-120 hover:bg-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Clear
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4 border-hairline border-t px-4 py-4">
        <div className="min-w-64 flex-1">
          <label
            htmlFor={rosterId}
            className="font-medium text-[12px] text-ink-muted uppercase tracking-wide"
          >
            Participants{" "}
            <span className="normal-case tracking-normal">(optional — pins name spelling)</span>
          </label>
          <input
            id={rosterId}
            type="text"
            value={roster}
            onChange={(e) => setRoster(e.target.value)}
            placeholder="e.g. Rina (PM), Dimas (Eng)"
            className="mt-1.5 h-9 w-full rounded-lg border border-hairline bg-sunken px-3 text-[14px] text-ink placeholder:text-ink-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <div className="flex items-center gap-3">
          <fieldset className="inline-flex rounded-lg border border-hairline bg-sunken p-0.5">
            <legend className="sr-only">Summary language</legend>
            {(["en", "id"] as const).map((lang) => (
              <button
                key={lang}
                type="button"
                aria-pressed={language === lang}
                onClick={() => pickLanguage(lang)}
                className={cn(
                  "rounded-[6px] px-3 py-1.5 font-medium text-[13px] text-ink-muted transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  language === lang && "bg-canvas text-ink shadow-none",
                )}
              >
                {lang === "en" ? "English" : "Bahasa"}
              </button>
            ))}
          </fieldset>
          <button
            type="button"
            disabled={!file || submitting}
            onClick={submit}
            className="h-9 rounded-lg bg-violet px-4 font-medium text-[14px] text-white transition-colors duration-120 hover:bg-violet-deep disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {submitting ? "Uploading…" : "Summarize"}
          </button>
        </div>
      </div>
    </div>
  );
}
