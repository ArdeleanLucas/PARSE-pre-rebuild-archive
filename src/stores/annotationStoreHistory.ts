import type { AnnotationRecord } from "../api/types";

// Deep-cloned pre-mutation snapshots. Session-only — never persisted, cleared
// when a speaker record is loaded/reloaded from the backend. The `label`
// surfaces in toasts ("Undid merge with next").
export interface HistoryEntry {
  snapshot: AnnotationRecord;
  label: string;
}

export interface SpeakerHistory {
  undo: HistoryEntry[];
  redo: HistoryEntry[];
}

export interface HistoryRestoreDelta {
  histories: Record<string, SpeakerHistory>;
  label: string;
  record: AnnotationRecord;
}

// Human-readable tier names for undo/redo labels. Surfaced verbatim in
// toasts ("Undid text edit (IPA)"), so keep these short and matched to the
// LANE_LABELS the user already sees in TranscriptionLanes where possible.
// Unknown/custom tiers fall through to the raw slug, which is still readable
// (e.g. a custom "gloss" tier shows as "Undid text edit (gloss)").
const TIER_LABEL: Record<string, string> = {
  ipa_phone: "Phones",
  ipa: "IPA",
  ortho: "ORTH",
  ortho_words: "ORTH words",
  stt: "STT",
  concept: "Concept",
  sentence: "Sentence",
  speaker: "Speaker",
};

export function tierLabel(tier: string): string {
  return TIER_LABEL[tier] ?? tier;
}

// Max undo-stack depth per speaker. Chosen to keep snapshot memory bounded
// for long annotation sessions on large records (a full AnnotationRecord
// with ~5k intervals across tiers is tens of KB; 50 snapshots ≈ a few MB
// per speaker in the worst case).
export const HISTORY_CAP = 50;

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

export function emptyHistory(): SpeakerHistory {
  return { undo: [], redo: [] };
}

/** Build the next histories object by pushing `pre` onto the speaker's undo
 * stack and clearing redo. Called from inside every mutator with the
 * pre-mutation record so the snapshot captures the state being left behind. */
export function pushHistoryDelta(
  histories: Record<string, SpeakerHistory>,
  speaker: string,
  pre: AnnotationRecord,
  label: string,
): Record<string, SpeakerHistory> {
  const prev = histories[speaker] ?? emptyHistory();
  const undo = [...prev.undo, { snapshot: deepClone(pre), label }];
  if (undo.length > HISTORY_CAP) undo.shift();
  return { ...histories, [speaker]: { undo, redo: [] } };
}

export function popUndoDelta(
  histories: Record<string, SpeakerHistory>,
  records: Record<string, AnnotationRecord>,
  speaker: string,
): HistoryRestoreDelta | null {
  const hist = histories[speaker];
  const current = records[speaker];
  if (!hist || hist.undo.length === 0 || !current) return null;

  const entry = hist.undo[hist.undo.length - 1];
  const nextUndo = hist.undo.slice(0, -1);
  const nextRedo = [...hist.redo, { snapshot: deepClone(current), label: entry.label }];

  return {
    label: entry.label,
    record: entry.snapshot,
    histories: {
      ...histories,
      [speaker]: { undo: nextUndo, redo: nextRedo },
    },
  };
}

export function popRedoDelta(
  histories: Record<string, SpeakerHistory>,
  records: Record<string, AnnotationRecord>,
  speaker: string,
): HistoryRestoreDelta | null {
  const hist = histories[speaker];
  const current = records[speaker];
  if (!hist || hist.redo.length === 0 || !current) return null;

  const entry = hist.redo[hist.redo.length - 1];
  const nextRedo = hist.redo.slice(0, -1);
  const nextUndo = [...hist.undo, { snapshot: deepClone(current), label: entry.label }];

  return {
    label: entry.label,
    record: entry.snapshot,
    histories: {
      ...histories,
      [speaker]: { undo: nextUndo, redo: nextRedo },
    },
  };
}
