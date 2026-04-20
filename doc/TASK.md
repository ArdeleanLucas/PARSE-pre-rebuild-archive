# ParseUI — Wiring Task List

> **File:** `src/ParseUI.tsx`
> **Branch target:** branch from `origin/main`
> **Last audited:** 2026-07-20
> **Items:** 46 total — 35 done, 10 partial, 1 still todo
> **Status:** living checklist — update after each PR that touches ParseUI wiring.

All items reference `src/ParseUI.tsx` on `main`. Line numbers are approximate and
shift with each PR — search by function/variable name instead of relying on exact lines.

---

## ✅ Section 1 — Data Still Mock / Hardcoded (9 items)

| # | What | Status | Evidence |
|---|---|---|---|
| 1 | `CONCEPTS` array used directly | ✅ DONE | Store-derived via `useConfigStore` → `rawConcepts` + `useMemo` |
| 2 | `SPEAKERS.length` in speaker-count display | ✅ DONE | Uses `speakers.length` from store |
| 3 | `SPEAKERS` in speaker select `<option>` list | ✅ DONE | `speakers.map(s => <option>)` |
| 4 | `MOCK_FORMS` object | 🟡 PARTIAL | `MOCK_FORMS` removed; `speakerForms` built from `annotationRecords` + `enrichmentData`, but `flagged` is concept-tag-based, not per-speaker annotation flag |
| 5 | `reviewed = 0` in progress bar | 🟡 PARTIAL | Now `concepts.filter(c => c.tag === 'confirmed').length` — tag-based, not "every speaker has an interval" logic as originally specified |
| 6 | Reference forms hardcoded Arabic/Persian | ✅ DONE | `resolveReferenceForms()` from `enrichments.reference_forms` |
| 7 | Borrowings alert — hardcoded `Fail01` | ✅ DONE | Borrowings panel is data-driven via `borrowingCandidates` |
| 8 | Status panel hardcoded strings | ✅ DONE | Dynamic `speakers.length` + `concepts.length` |
| 9 | `"Missing"` badge on concept header | ✅ DONE | Badge based on `annotated` boolean from `findAnnotationForConcept` |

---

## ✅ Section 2 — Annotate Mode Actions (7 items)

| # | What | Status | Evidence |
|---|---|---|---|
| 10 | IPA field — local state only | 🟡 PARTIAL | Loads from store via `findAnnotationForConcept`; local `useState` for editing; persisted only on Save click (design choice, not a bug) |
| 11 | Ortho field — same issue | 🟡 PARTIAL | Same pattern as IPA — local edit, persist on Save |
| 12 | **Save Annotation** button | ✅ DONE | Creates/updates intervals + `saveSpeaker(speaker)` |
| 13 | **Mark Done** button | ✅ DONE | `tagConcept('confirmed', concept.key)` |
| 14 | **SkipBack** (prev segment) button | ✅ DONE | Previous interval lookup + seek via `skip()` |
| 15 | Right-rail **Save annotations** button | ✅ DONE | Calls `saveSpeaker(speaker)` |
| 16 | Spectrogram toggle | ✅ DONE | `useSpectrogram` hook + canvas rendering when `spectroOn` |

---

## ✅ Section 3 — Compare Mode Actions (14 items)

| # | What | Status | Evidence |
|---|---|---|---|
| 17 | **Accept** concept button | ✅ DONE | `tagConcept('confirmed', concept.key)` |
| 18 | **Flag** concept header button | ✅ DONE | `tagConcept('problematic', concept.key)` |
| 19 | Reference form audio **play** buttons | ✅ DONE | `new Audio(entry.data.audioUrl).play()` |
| 20 | Cognate **Accept grouping** button | ✅ DONE | Patches `cognate_decisions` + `save()` |
| 21 | Cognate **Split** button | ✅ DONE | `decision: 'split'` + `save()` |
| 22 | Cognate **Merge** button | ✅ DONE | `decision: 'merge'` + `save()` |
| 23 | Cognate **Cycle** button | ✅ DONE | Computes next option + `save()` |
| 24 | Borrowings section reactive to concept | ✅ DONE | `borrowingCandidates` depends on `[concept, enrichmentData]` |
| 25 | **Notes** field persisted | 🟡 PARTIAL | Persisted to `localStorage` (`parseui-compare-notes-v1`), not to store/API decisions |
| 26 | Right-rail **Compute: Run** button | ✅ DONE | `startComputeJob()` via `useComputeJob` |
| 27 | Right-rail **Compute: Refresh** button | ✅ DONE | `useEnrichmentStore.getState().load()` |
| 28 | Right-rail **Save decisions** button | ✅ DONE | Creates JSON blob + downloads `parse-decisions.json` |
| 29 | Right-rail **Load decisions** button | ✅ DONE | File picker → parse JSON → save to enrichment store |
| 30 | Per-speaker row **flag** | 🟡 PARTIAL | Clickable, toggles `tagConcept`/`untagConcept` — but mutates concept tag globally, not per-speaker annotation record flag |

---

## ✅ Section 4 — Actions Menu Items (9 items)

| # | Menu label | Status | Evidence |
|---|---|---|---|
| 31 | **Import Speaker Data** | ✅ DONE | Opens `SpeakerImport` modal via `openImportModal` |
| 32 | **Run Audio Normalization** | ✅ DONE | `normalizeJob.run()` → `startNormalize` + `pollNormalize` |
| 33 | **Run Orthographic STT** | ✅ DONE | `sttJob.run()` → `startSTT` + `pollSTT` |
| 34 | **Run IPA Transcription** | ✅ DONE | `ipaJob.run()` → `startCompute('ipa_only')` |
| 35 | **Run Full Pipeline** | 🟡 PARTIAL | Single backend job `startCompute('full_pipeline')` — not sequential 31→32→33→34 orchestration as originally described |
| 36 | **Run Cross-Speaker Match** | ✅ DONE | `crossSpeakerJob.run()` → `startCompute('contact-lexemes')` |
| 37 | **Load Decisions** | ✅ DONE | File picker → parse JSON → save to store |
| 38 | **Save Decisions** | 🔴 STILL TODO | Button only closes dropdown — no save/export action wired |
| 39 | **Reset Project** | 🟡 PARTIAL | Clears Zustand stores but does not clear `localStorage` |

---

## ✅ Section 5 — Tags Mode Concept Assignment (3 items)

| # | What | Status | Evidence |
|---|---|---|---|
| 40 | Concept checkboxes — `onChange` | ✅ DONE | Toggles `tagConcept` / `untagConcept` |
| 41 | **Apply to selected** button | ✅ DONE | Iterates `checkedConceptIds` → `tagConcept` each |
| 42 | **Clear selection** button | ✅ DONE | `setCheckedConceptIds(new Set())` |

---

## ✅ Section 6 — Minor Cleanup / Stale Comments (4 items)

| # | What | Status | Evidence |
|---|---|---|---|
| 43 | Old TODO comment block about mock waveform | ✅ DONE | Not present in current file |
| 44 | `{/* TODO: Replace mock with real hook */}` comment | ✅ DONE | Removed. One residual TODO remains: `// TODO: wire to real borrowing data from enrichments` (~line 1481) |
| 45 | `useEffect` in `AIChat` depends on stale `messages` | ✅ DONE | Now depends on `chatSession.messages` |
| 46 | `SPEAKERS.length` → `speakers.length` | ✅ DONE | No `SPEAKERS` constant remaining |

---

## Priority Order (updated)

```
DONE — No action needed
  #1,#2,#3,#6,#7,#8,#9   (Section 1 data swaps)
  #12,#13,#14,#15,#16     (Section 2 annotate actions)
  #17–#24,#26–#29         (Section 3 compare actions)
  #31–#34,#36,#37         (Section 4 actions menu)
  #40,#41,#42             (Section 5 tags)
  #43,#44,#45,#46         (Section 6 cleanup)

PARTIAL — Acceptable design choices or minor gaps
  #4   (flagged is concept-tag-based, not per-speaker)
  #5   (reviewed count is tag-based, not interval-coverage)
  #10  (IPA: local edit → persist on Save — reasonable UX)
  #11  (Ortho: same pattern)
  #25  (Notes: localStorage only, not API-persisted)
  #30  (Per-speaker flag: global concept tag, not per-speaker)
  #35  (Full Pipeline: single job, not sequential orchestration)
  #39  (Reset: clears stores but not localStorage)

STILL TODO — Needs fix
  #38  (Save Decisions in Actions menu — button is a no-op)
```

---

## Related Files

| File | Role | Exists? |
|---|---|---|
| `src/ParseUI.tsx` | Primary file — all items reference this | ✅ |
| `src/hooks/useWaveSurfer.ts` | WaveSurfer lifecycle — items 14, 19 | ✅ |
| `src/hooks/useAnnotationSync.ts` | Annotation persistence — items 10–12, 25 | ✅ |
| `src/hooks/useChatSession.ts` | Chat — item 45 | ✅ |
| `src/hooks/useImportExport.ts` | Import/export — items 28, 29, 37, 38 | ✅ |
| `src/stores/annotationStore.ts` | Annotation records — items 4, 9–13, 20–23, 25, 30 | ✅ |
| `src/stores/configStore.ts` | Speakers + concepts — items 1–3, 8 | ✅ |
| `src/stores/enrichmentStore.ts` | Enrichments + reference forms — items 4, 6, 7, 24, 27 | ✅ |
| `src/stores/tagStore.ts` | Tag assignments — items 13, 17, 18, 40–42 | ✅ |
| `src/workers/spectrogram-worker.ts` | Spectrogram — item 16 | ✅ |
| `python/server.py` | All API endpoints — items 26, 31–38 | ✅ |
