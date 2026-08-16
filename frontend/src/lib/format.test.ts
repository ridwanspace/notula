import { describe, expect, it } from "vitest";
import { formatCost, formatDuration, formatTimestamp } from "@/lib/format";

describe("formatTimestamp", () => {
  it("renders MM:SS under an hour", () => {
    expect(formatTimestamp(0)).toBe("00:00");
    expect(formatTimestamp(65.9)).toBe("01:05");
    expect(formatTimestamp(599)).toBe("09:59");
  });

  it("renders H:MM:SS past an hour", () => {
    expect(formatTimestamp(3661)).toBe("1:01:01");
  });

  it("clamps negatives to zero", () => {
    expect(formatTimestamp(-3)).toBe("00:00");
  });
});

describe("formatDuration", () => {
  it("renders m:ss and an em dash for unknown", () => {
    expect(formatDuration(60)).toBe("1:00");
    expect(formatDuration(90.4)).toBe("1:30");
    expect(formatDuration(null)).toBe("—");
  });
});

describe("formatCost", () => {
  it("shows n/a for unpriced models", () => {
    expect(formatCost(null)).toBe("n/a");
  });

  it("keeps precision on tiny values and none on zero", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(0.0046305)).toBe("$0.00463");
    expect(formatCost(1.5)).toBe("$1.50");
  });
});
