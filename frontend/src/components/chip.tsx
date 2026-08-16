import { stateChip } from "@/lib/states";
import { cn } from "@/lib/utils";

export function StateChip({ state }: { state: string }) {
  const chip = stateChip(state);
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-lg border px-2 font-medium text-[12px]",
        chip.className,
      )}
    >
      {chip.pulse && <span className="size-1.5 animate-pulse rounded-full bg-violet-deep" />}
      {chip.label}
    </span>
  );
}
