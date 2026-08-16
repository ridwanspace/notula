import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PipelineTable } from "@/components/pipeline-table";
import type { Stage } from "@/lib/api/client";

const stages: Stage[] = [
  {
    stage: "normalize",
    seconds: 0.09,
    model: "",
    cost_usd: null,
    input_tokens: 0,
    output_tokens: 0,
    detail: "",
  },
  {
    stage: "transcribe",
    seconds: 8.72,
    model: "gemini-3.5-flash",
    cost_usd: 0.0046305,
    input_tokens: 1617,
    output_tokens: 245,
    detail: "",
  },
];

describe("PipelineTable", () => {
  it("shows n/a for unpriced stages and a total that flags them", () => {
    render(<PipelineTable stages={stages} />);
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.getByText("$0.00463")).toBeInTheDocument();
    expect(screen.getByText(/\+ 1 unpriced/)).toBeInTheDocument();
  });

  it("renders tokens from usage metadata per stage", () => {
    render(<PipelineTable stages={stages} />);
    expect(screen.getAllByText(/1,617 in \/ 245 out/).length).toBeGreaterThan(0);
  });
});
