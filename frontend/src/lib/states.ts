export const ACTIVE_STATES = ["uploaded", "normalizing", "transcribing", "summarizing"] as const;

export function isActiveState(state: string): boolean {
  return (ACTIVE_STATES as readonly string[]).includes(state);
}

export interface ChipStyle {
  label: string;
  className: string;
  pulse: boolean;
}

/**
 * State chips stay inside the accent contract: neutral grey for settled
 * states, violet only while the pipeline is the thing talking, danger for
 * failure. All pairings are ink-on-tint at >= 4.5:1.
 */
export function stateChip(state: string): ChipStyle {
  if (state === "completed") {
    return {
      label: "Completed",
      className: "bg-sunken text-ink-body border-hairline",
      pulse: false,
    };
  }
  if (state === "failed") {
    return {
      label: "Failed",
      className: "bg-danger-wash text-[#b03a30] border-[#f0d4d1]",
      pulse: false,
    };
  }
  if (isActiveState(state)) {
    const label = state.charAt(0).toUpperCase() + state.slice(1);
    return { label, className: "bg-ai-wash text-violet-deep border-violet/20", pulse: true };
  }
  return { label: state, className: "bg-sunken text-ink-muted border-hairline", pulse: false };
}
