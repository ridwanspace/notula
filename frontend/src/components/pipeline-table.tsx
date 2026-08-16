import type { Stage } from "@/lib/api/client";
import { formatCost, formatSeconds } from "@/lib/format";

/** Per-stage measured wall time, tokens, and cost. Unpriced models show "n/a". */
export function PipelineTable({ stages }: { stages: Stage[] }) {
  const priced = stages.filter((s) => s.cost_usd != null);
  const unpriced = stages.length - priced.length;
  const total = priced.reduce((sum, s) => sum + (s.cost_usd ?? 0), 0);
  const totalLabel = `${formatCost(total)}${unpriced > 0 ? ` + ${unpriced} unpriced` : ""}`;

  return (
    <div>
      <ul className="space-y-3">
        {stages.map((stage) => (
          <li key={stage.stage} className="text-[13px]">
            <div className="flex items-baseline justify-between">
              <span className="font-medium text-ink">{stage.stage}</span>
              <span className="text-ink-body tabular-nums">{formatCost(stage.cost_usd)}</span>
            </div>
            <div className="mt-0.5 flex items-baseline justify-between text-[12px] text-ink-muted">
              <span className="font-mono">{stage.model || "—"}</span>
              <span className="tabular-nums">
                {formatSeconds(stage.seconds)} · {stage.input_tokens.toLocaleString()} in /{" "}
                {stage.output_tokens.toLocaleString()} out
              </span>
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-baseline justify-between border-hairline border-t pt-2 text-[13px]">
        <span className="font-medium text-ink">Total</span>
        <span className="text-ink tabular-nums">{totalLabel}</span>
      </div>
      <p className="mt-2 text-[12px] text-ink-muted leading-4">
        Tokens from provider usage metadata; costs from the published price table.
      </p>
    </div>
  );
}
