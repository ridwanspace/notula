import { describe, expect, it } from "vitest";
import { isActiveState, stateChip } from "@/lib/states";

describe("isActiveState", () => {
  it("marks pipeline states active and terminal states not", () => {
    for (const s of ["uploaded", "normalizing", "transcribing", "summarizing"]) {
      expect(isActiveState(s)).toBe(true);
    }
    expect(isActiveState("completed")).toBe(false);
    expect(isActiveState("failed")).toBe(false);
  });
});

describe("stateChip", () => {
  it("keeps settled states achromatic and reserves violet for activity", () => {
    expect(stateChip("completed").className).toContain("bg-sunken");
    expect(stateChip("completed").pulse).toBe(false);
    expect(stateChip("transcribing").className).toContain("violet");
    expect(stateChip("transcribing").pulse).toBe(true);
    expect(stateChip("failed").className).toContain("danger");
  });

  it("labels unknown states verbatim without pulsing", () => {
    const chip = stateChip("archived");
    expect(chip.label).toBe("archived");
    expect(chip.pulse).toBe(false);
  });
});
