import type { components } from "./types";

export type Meeting = components["schemas"]["MeetingOut"];
export type MeetingDetail = components["schemas"]["MeetingDetailOut"];
export type Summary = components["schemas"]["SummaryOut"];
export type Stage = components["schemas"]["StageOut"];
export type TranscriptData = components["schemas"]["TranscriptOut"];
export type Utterance = components["schemas"]["UtteranceOut"];
export type ActionItem = components["schemas"]["ActionItemOut"];
export type Health = components["schemas"]["HealthOut"];
export type SummaryLanguage = "en" | "id";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Two routes and five endpoints: plain fetch is the whole data layer. A cache
// library (TanStack Query) earns its weight with competing consumers and
// invalidation races — here it would be dependency theater.
async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listMeetings: (): Promise<{ meetings: Meeting[] }> =>
    fetch("/api/meetings").then((r) => unwrap(r)),

  getMeeting: (id: string): Promise<MeetingDetail> =>
    fetch(`/api/meetings/${id}`).then((r) => unwrap(r)),

  submitMeeting: (
    file: File,
    roster: string,
    language: SummaryLanguage,
  ): Promise<{ id: string }> => {
    const form = new FormData();
    form.append("file", file);
    form.append("roster", roster);
    form.append("language", language);
    return fetch("/api/meetings", { method: "POST", body: form }).then((r) => unwrap(r));
  },

  resummarize: (id: string, language: SummaryLanguage): Promise<Summary> =>
    fetch(`/api/meetings/${id}/summaries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language }),
    }).then((r) => unwrap(r)),

  health: (): Promise<Health> => fetch("/healthz").then((r) => unwrap(r)),

  audioUrl: (id: string): string => `/api/meetings/${id}/audio`,
  eventsUrl: (id: string): string => `/api/meetings/${id}/events`,
};
