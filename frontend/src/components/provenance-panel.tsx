import { cn } from "@/lib/utils";

/**
 * The signature surface: AI-authored content sits in a violet-washed container
 * with ONE caption row for the whole panel — provenance is a surface, never a
 * per-item badge. Accent text on the tint uses the darkened companion token.
 */
export function ProvenancePanel({
  model,
  repairAttempts = 0,
  className,
  children,
}: {
  model: string;
  repairAttempts?: number;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-xl border border-violet/25 bg-ai-panel p-5", className)}>
      <p className="font-medium text-[12px] text-violet-deep">
        ✦ AI-generated · {model} · pass 2{repairAttempts > 0 && ` · ${repairAttempts} repairs`}
      </p>
      <div className="mt-4">{children}</div>
    </section>
  );
}
