/** Seconds → "MM:SS", or "H:MM:SS" past an hour. */
export function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ms = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return h > 0 ? `${h}:${ms}` : ms;
}

/** Audio duration for meta rows: "1:00", "—" when unknown. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Stage cost: null → "n/a" (unpriced model), tiny values keep precision. */
export function formatCost(cost: number | null | undefined): string {
  if (cost == null) return "n/a";
  if (cost === 0) return "$0.00";
  return `$${cost < 0.01 ? cost.toFixed(5) : cost.toFixed(2)}`;
}

export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(seconds < 10 ? 2 : 1)}s`;
}
