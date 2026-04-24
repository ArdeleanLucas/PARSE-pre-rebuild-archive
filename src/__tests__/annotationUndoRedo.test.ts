import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: vi.fn(),
  saveAnnotation: vi.fn().mockResolvedValue(undefined),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
}));

import { useAnnotationStore } from "../stores/annotationStore";
import type { AnnotationRecord } from "../api/types";

function seed(): AnnotationRecord {
  return {
    speaker: "S1",
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 2,
        intervals: [
          { start: 0, end: 1, text: "a" },
          { start: 1, end: 2, text: "b" },
          { start: 2, end: 3, text: "c" },
        ],
      },
      stt: { name: "stt", display_order: 5, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    source_wav: "x.wav",
  };
}

describe("annotationStore undo/redo", () => {
  beforeEach(() => {
    useAnnotationStore.setState({
      records: { S1: seed() },
      dirty: { S1: false },
      loading: {},
      histories: {},
    });
  });

  it("undo restores pre-merge state after merge-with-next", () => {
    const store = useAnnotationStore.getState();
    store.mergeIntervals("S1", "ipa", 0);

    const merged = useAnnotationStore.getState().records.S1.tiers.ipa.intervals;
    expect(merged).toHaveLength(2);
    expect(merged[0]).toEqual({ start: 0, end: 2, text: "a b" });

    const label = useAnnotationStore.getState().undo("S1");
    expect(label).toContain("merge");

    const restored = useAnnotationStore.getState().records.S1.tiers.ipa.intervals;
    expect(restored).toHaveLength(3);
    expect(restored.map((i) => i.text)).toEqual(["a", "b", "c"]);
  });

  it("redo re-applies the merge after an undo", () => {
    const store = useAnnotationStore.getState();
    store.mergeIntervals("S1", "ipa", 1);
    useAnnotationStore.getState().undo("S1");
    useAnnotationStore.getState().redo("S1");

    const ivs = useAnnotationStore.getState().records.S1.tiers.ipa.intervals;
    expect(ivs).toHaveLength(2);
    expect(ivs[1]).toEqual({ start: 1, end: 3, text: "b c" });
  });

  it("updateInterval / undo swaps text back", () => {
    useAnnotationStore.getState().updateInterval("S1", "ipa", 0, "X");
    expect(useAnnotationStore.getState().records.S1.tiers.ipa.intervals[0].text).toBe("X");
    useAnnotationStore.getState().undo("S1");
    expect(useAnnotationStore.getState().records.S1.tiers.ipa.intervals[0].text).toBe("a");
  });

  it("new mutation clears the redo stack", () => {
    useAnnotationStore.getState().updateInterval("S1", "ipa", 0, "X");
    useAnnotationStore.getState().undo("S1");
    expect(useAnnotationStore.getState().histories.S1.redo).toHaveLength(1);
    useAnnotationStore.getState().updateInterval("S1", "ipa", 0, "Y");
    expect(useAnnotationStore.getState().histories.S1.redo).toHaveLength(0);
  });

  it("history caps at 50 entries per speaker", () => {
    for (let i = 0; i < 60; i += 1) {
      useAnnotationStore.getState().updateInterval("S1", "ipa", 0, `t${i}`);
    }
    expect(useAnnotationStore.getState().histories.S1.undo).toHaveLength(50);
  });

  it("undo returns null when stack is empty", () => {
    expect(useAnnotationStore.getState().undo("S1")).toBeNull();
  });

  it("ensureSttTier copies segments and is idempotent", () => {
    const segs = [
      { start: 0, end: 1, text: "one" },
      { start: 1, end: 2, text: "two" },
    ];
    useAnnotationStore.getState().ensureSttTier("S1", segs);
    let stt = useAnnotationStore.getState().records.S1.tiers.stt.intervals;
    expect(stt).toEqual(segs);

    // Second call must not re-migrate or push another history entry.
    const histLenBefore = useAnnotationStore.getState().histories.S1.undo.length;
    useAnnotationStore.getState().ensureSttTier("S1", [
      { start: 5, end: 6, text: "nope" },
    ]);
    stt = useAnnotationStore.getState().records.S1.tiers.stt.intervals;
    expect(stt).toEqual(segs);
    expect(useAnnotationStore.getState().histories.S1.undo).toHaveLength(histLenBefore);
  });

  it("undo after ensureSttTier restores the empty-tier state", () => {
    useAnnotationStore.getState().ensureSttTier("S1", [
      { start: 0, end: 1, text: "one" },
    ]);
    useAnnotationStore.getState().undo("S1");
    expect(useAnnotationStore.getState().records.S1.tiers.stt.intervals).toHaveLength(0);
  });
});
