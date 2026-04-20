# Docs Audit — 2026-04-20

**Scope:** every file under `docs/` (6 top-level + 22 in `plans/` + 13 in `plans/oda/` = 41 files).

**Project goals driving the audit:**

1. React UI + Python backend (current architecture: `src/` React/TS, `python/` backend).
2. Remove **all** vanilla JS from the project (root `js/` dir, `parse.html`, `compare.html`, `review_tool_dev.html`, legacy launchers).
3. Speaker onboarding must offer a choice between xAI and OpenAI providers.
4. No mock / demo / fixture data in runtime code.

Verdict legend: **KEEP** · **UPDATE** · **OBSOLETE** · **UNCERTAIN**.

---

## Code-state reality check (used to grade each doc)

- **React UI is the live surface.** Root `index.html` bootstraps `src/main.tsx` only. `src/` has all modes (Annotate, Compare, Tags) as React components with Zustand stores, typed API client, Vitest coverage.
- **Legacy vanilla JS is still on disk but orphaned from the React app.** `js/` (25 files, ~1.3 MB), `parse.html`, `compare.html`, `review_tool_dev.html` still exist. Only `compare.html` (14 `<script>` refs) and `review_tool_dev.html` (12 refs) load from `js/`. `parse.html` is a self-contained legacy monolith. `vite.config.ts:5–23` ships a `forceSpaCompareRoute` plugin whose comment openly states it exists *because* `compare.html` is still at the repo root.
- **Launchers are split.** `scripts/parse-run.sh` and `run-parse.sh` launch the React stack correctly (Python `server.py` + `npx vite`). `start_parse.sh` and `Start Review Tool.bat` still try to launch a non-existent `python/thesis_server.py` and open `review_tool_dev.html`; both bail with an error on a fresh checkout and each already carries a comment pointing users to the React launcher.
- **No mock data in runtime code.** `grep` for `mock|fixture|demo|stub|fakeData` across `src/` non-test files returns zero hits. `src/ParseUI.tsx:54` explicitly asserts `// No fallback data — workspace must supply real speakers and concepts via /api/config.` Python runtime code is equally clean — all `sample`/`mock` hits are either `sample_rate` (DSP) or test-only.
- **xAI and OpenAI are both registered providers.** `python/ai/provider.py:1091` (`XAIProvider` hitting `https://api.x.ai/v1`, env `XAI_API_KEY`) and `python/ai/provider.py:929` (`OpenAIProvider`). Dispatcher at `provider.py:1254` routes `xai`/`grok`/`x.ai` to `XAIProvider`. LLM/chat auth UI in `src/ParseUI.tsx:243,518,537` and `src/components/annotate/ChatPanel.tsx:57–59` already exposes both providers for key entry.
- **Speaker onboarding exists but is provider-blind.** `POST /api/onboard/speaker` (`python/server.py:2166–2414`) accepts `speaker_id` + audio WAV + optional CSV. React UI at `src/components/compare/SpeakerImport.tsx:106–159` calls `onboardSpeaker()` (`src/api/client.ts:290–316`). There is **no `provider` parameter** on the call or form — onboarding uses whichever provider the user last authed globally. To meet goal #3 this needs an explicit xAI/OpenAI selector in `SpeakerImport.tsx` and a `provider` field on the `/api/onboard/speaker` payload.

---

## Top-level `docs/`

| File | Size | Verdict | Reason |
|---|---|---|---|
| [`BUILD_SESSION.md`](BUILD_SESSION.md) | 11 KB | **OBSOLETE** | Wave-based build plan for vanilla-JS modules (`js/annotation-store.js`, `js/annotation-panel.js`, …) and `window.SourceExplorer`→`window.PARSE` namespace migration. All superseded by the React rewrite. |
| [`ONBOARDING_PLAN.md`](ONBOARDING_PLAN.md) | 11 KB | **UPDATE** | Import-wizard design for speaker onboarding (WAV + timestamp CSV + IPA CSV + AI matching). Conceptually aligned with goal #3, but assumes Anthropic Claude as default AI and Ollama fallback — needs rewriting to require xAI/OpenAI selection and to match the current `POST /api/onboard/speaker` contract (not the wizard flow it describes). |
| [`SPEAKERS.md`](SPEAKERS.md) | 7.6 KB | **UPDATE** | Personal thesis data inventory (speaker tiers, WSL `/mnt/c/…` paths, per-speaker transcription CSVs). Useful as a reference for the author's own research data, but the paths are WSL-specific and conflict with `desktop_product_architecture.md`'s portability rules. Move to a research-notes subfolder or strip machine-specific paths. |
| [`desktop_product_architecture.md`](desktop_product_architecture.md) | 18 KB | **UPDATE** | Canonical living plan for Electron + local Python packaging. Architecture direction still correct and lists xAI/OpenAI/Ollama as optional cloud-AI tier (§9.1). However §3 diagram, §16 "Stream 3 — Frontend unification path", and §17 (blockers #2, #7) all reference `parse.html`/`compare.html`/legacy JS as live surface. Refresh: delete vanilla-JS references, promote `src/` React as the sole frontend, add explicit "remove `js/` + `*.html` legacy pages" as a Phase-0 deliverable. |
| [`distribution_readiness_checklist.md`](distribution_readiness_checklist.md) | 7.7 KB | **UPDATE** | Companion checklist to the architecture doc. Mostly goal-aligned, but "Known current blockers" lists Annotate-mode-monolithic-localStorage and legacy launcher references that are stale (Annotate is now React, React launchers exist). Refresh the blocker list; add "`js/`, `parse.html`, `compare.html`, `review_tool_dev.html` removed" and "`start_parse.sh`, `Start Review Tool.bat` removed or rewritten for React" to Gate A / D2. |
| [`runtime_paths_foundation.md`](runtime_paths_foundation.md) | 4.5 KB | **KEEP** | Pure Python helper spec for `python/shared/app_paths.py` + `runtime_config.py`. No vanilla-JS references. Goal-aligned (cross-platform packaging). |

---

## `docs/plans/`

| File | Verdict | Reason |
|---|---|---|
| [`MC-300-parseui-recovery.md`](plans/MC-300-parseui-recovery.md) | **OBSOLETE** | Self-labeled historical; Priority-1 wiring tasks all landed. |
| [`MC-301-parseui-actions-import.md`](plans/MC-301-parseui-actions-import.md) | **OBSOLETE** | Self-labeled historical; landed in PR #18. |
| [`MC-305-branch-cleanup-findings-pr.md`](plans/MC-305-branch-cleanup-findings-pr.md) | **OBSOLETE** | Task-complete; rolling-branch policy it assumes is gone. |
| [`MC-306-parseui-current-state-plan.md`](plans/MC-306-parseui-current-state-plan.md) | **OBSOLETE** | Replacement doc (`parseui-current-state-plan.md`) already exists. |
| [`MC-312-own-data-vs-filler-investigation.md`](plans/MC-312-own-data-vs-filler-investigation.md) | **KEEP** | Mock/fixture/fallback investigation — directly supports goal #4. Checklist still actionable (though `src/ParseUI.tsx:54` suggests most of the hunt is done — close it out once verified). |
| [`actions-job-lifecycle-pr.md`](plans/actions-job-lifecycle-pr.md) | **OBSOLETE** | `useActionJob` hook spec; shipped in PR #38. |
| [`compare-branch-audit.md`](plans/compare-branch-audit.md) | **OBSOLETE** | One-time branch audit; decision acted on. |
| [`contact-lexeme-fetcher.md`](plans/contact-lexeme-fetcher.md) | **KEEP** | Contact-language IPA fetcher using xAI/Grok + Wiktionary/CSV. Python backend + React `ContactLexemePanel`. Aligns with goals #1 and #3; parts still partially implemented. |
| [`generic-comparison-data-pipeline.md`](plans/generic-comparison-data-pipeline.md) | **KEEP** | Provider-registry design extending the contact-lexeme fetcher (xAI Grokipedia, ASJP, CLDF, Wikidata). Core plumbing on `main`, expansion roadmap still relevant. |
| [`github-branch-cleanup-findings-2026-04-10.md`](plans/github-branch-cleanup-findings-2026-04-10.md) | **OBSOLETE** | Self-labeled historical; cleanup done. |
| [`legacy-entrypoint-inventory.md`](plans/legacy-entrypoint-inventory.md) | **KEEP** | Canonical list of every remaining `parse.html`/`compare.html`/`js/`/`localhost:8766` reference. Directly supports goal #2. Highly actionable — use as the checklist for the vanilla-JS removal PR. |
| [`lexibank-setup.md`](plans/lexibank-setup.md) | **KEEP** | Operational setup doc for the Python-side CLDF/CLEF dataset pipeline. No JS surface, no mock data. |
| [`mc-308-audio-pipeline-fix.md`](plans/mc-308-audio-pipeline-fix.md) | **OBSOLETE** | All criteria marked done; shipped PR #43. |
| [`parsebuilder-todo.md`](plans/parsebuilder-todo.md) | **UPDATE** | Active owner TODO, but references retired C5/C6 gate workflow and stale completion dates. Refresh to the new goals (vanilla-JS deletion, xAI/OpenAI onboarding, no mock data). |
| [`parseui-current-state-plan.md`](plans/parseui-current-state-plan.md) | **UPDATE** | Best candidate for the canonical React-side plan. Aligned with React+Python. §1 and §3 marked done (PR #33, #38). Refresh with explicit sections for "remove vanilla JS entrypoints" and "xAI/OpenAI onboarding selector"; drop C5/C6/C7 vocabulary if that process is retired. |
| [`parseui-wiring-todo.md`](plans/parseui-wiring-todo.md) | **OBSOLETE** | Self-labeled archive of the vanilla-JS-era wiring TODO; points to the current-state plan. |
| [`pr38-dispatch-specs.md`](plans/pr38-dispatch-specs.md) | **OBSOLETE** | Implementation brief for landed PR #38. |
| [`pr38-role-split.md`](plans/pr38-role-split.md) | **OBSOLETE** | Agent-handoff coordination for landed PR #38. |
| [`react-vite-pivot.md`](plans/react-vite-pivot.md) | **UPDATE** | 47 KB foundational plan for the JS→React pivot. Load-bearing technical content (Python API contract + `js/`→React migration map) is still useful but phase tracker is stale. Trim to: (a) Python API contract as authoritative reference, (b) `js/`→React migration map as the deletion checklist. Drop branch/phase churn. |
| [`repo-cleanup-preflight.md`](plans/repo-cleanup-preflight.md) | **OBSOLETE** | One-time 2026-04-09 branch snapshot; list now fully pruned. |
| [`repo-state-cleanup-and-architecture-unification.md`](plans/repo-state-cleanup-and-architecture-unification.md) | **UPDATE** | Phase-5 task 5.1/5.2 is *exactly* the vanilla-JS deletion + Python-serves-`dist/` cutover goal #2 needs. Phases 0–4 and 6 are largely done. Strip to the Phase-5 plan; remove C5/C6 gating language now that the architecture is confirmed. |
| [`worktree-setup.md`](plans/worktree-setup.md) | **UPDATE** | Multi-agent worktree ops doc. Still useful but references stale branch names and the uppercase archival clone. Trim historical-notes section; confirm the current agent roster. |

---

## `docs/plans/oda/`

"ODA" was a named agent persona owning Track B (Compare Mode) of a dual-agent React+Vite pivot. `oda-core.md:93` logs a 2026-04-08 audit that rebuilt Oda's work from scratch, and every B-component it scoped (`ConceptTable`, `CognateControls`, `BorrowingPanel`, `TagManager`, `EnrichmentsPanel`, `SpeakerImport`, `useExport`, `useComputeJob`, `CompareMode`) exists in `src/components/compare/` and `src/hooks/` today. The entire track is landed.

| File | Verdict | Reason |
|---|---|---|
| [`b1-concept-table.md`](plans/oda/b1-concept-table.md) | **OBSOLETE** | `src/components/compare/ConceptTable.tsx` landed. |
| [`b2-cognate-controls.md`](plans/oda/b2-cognate-controls.md) | **OBSOLETE** | `CognateControls.tsx` landed. |
| [`b3-borrowing-panel.md`](plans/oda/b3-borrowing-panel.md) | **OBSOLETE** | `BorrowingPanel.tsx` landed. |
| [`b4-tag-manager.md`](plans/oda/b4-tag-manager.md) | **OBSOLETE** | `TagManager.tsx` landed. |
| [`b5-enrichments-panel.md`](plans/oda/b5-enrichments-panel.md) | **OBSOLETE** | `EnrichmentsPanel.tsx` landed. |
| [`b6-speaker-import.md`](plans/oda/b6-speaker-import.md) | **UPDATE** | Component exists (`SpeakerImport.tsx`), but the real flow is WAV+CSV upload to `/api/onboard/speaker`, not the JSON state-machine this spec describes. Drift. Either archive or rewrite to reflect the real onboarding contract (and add the xAI/OpenAI provider selector goal #3 requires). |
| [`b7-export.md`](plans/oda/b7-export.md) | **OBSOLETE** | `useExport.ts` landed; LingPy/NEXUS endpoints wired in `client.ts`. |
| [`b8-compute-job.md`](plans/oda/b8-compute-job.md) | **OBSOLETE** | `useComputeJob.ts` landed. |
| [`b9-compare-mode.md`](plans/oda/b9-compare-mode.md) | **OBSOLETE** | `CompareMode.tsx` assembled per checklist. |
| [`coordination.md`](plans/oda/coordination.md) | **OBSOLETE** | Oda↔ParseBuilder handoff protocol; Track B audit already closed it. |
| [`oda-core.md`](plans/oda/oda-core.md) | **OBSOLETE** | Self-labels its branch notes as historical; build status records completion. |
| [`phase-0.md`](plans/oda/phase-0.md) | **OBSOLETE** | Scaffold gate long passed. |
| [`rules.md`](plans/oda/rules.md) | **UPDATE** | Most engineering rules (Zustand, strict TS, no inline styles, no `window.PARSE`) are still sound. They are scoped to "Track B" / Oda and cite historical branch names. Lift the still-valid rules into `AGENTS.md` (or a top-level `CONTRIBUTING.md`) and delete this file. |

**Recommendation for the whole `oda/` folder:** archive wholesale. Move to `docs/plans/archive/oda/` or delete after extracting `rules.md`'s still-valid items into `AGENTS.md`. Update `b6-speaker-import.md` first if it will stay referenced.

---

## Summary counts

| Bucket | Top-level | `plans/` | `plans/oda/` | Total |
|---|---|---|---|---|
| **KEEP** | 1 | 5 | 0 | **6** |
| **UPDATE** | 4 | 5 | 2 | **11** |
| **OBSOLETE** | 1 | 12 | 11 | **24** |
| **UNCERTAIN** | 0 | 0 | 0 | **0** |
| Total | 6 | 22 | 13 | **41** |

Roughly **59 %** of `docs/` is historical — documentation of landed work, finished cleanups, or the pre-React architecture. Archiving or deleting these would make the surviving plans easier to find and trust.

---

## Recommended follow-up actions

Not part of this PR — this PR is the audit itself. Open these as separate tickets:

1. **Archive obsolete docs** — move the 24 OBSOLETE files into `docs/plans/archive/` (or delete outright). Most already self-label as historical.
2. **Execute the vanilla-JS deletion** per [`legacy-entrypoint-inventory.md`](plans/legacy-entrypoint-inventory.md) + [`repo-state-cleanup-and-architecture-unification.md`](plans/repo-state-cleanup-and-architecture-unification.md) Phase 5. Targets: `js/`, `parse.html`, `compare.html`, `review_tool_dev.html`, `start_parse.sh`, `Start Review Tool.bat`, and the `forceSpaCompareRoute` plugin in `vite.config.ts:5–23`. Confirm nothing else references them first.
3. **Add xAI/OpenAI selector to speaker onboarding** — extend `POST /api/onboard/speaker` (`python/server.py:2166`) to accept a `provider` field (`xai` | `openai`), thread it to `_run_onboard_speaker_job` (`server.py:1633`), add a provider radio to `src/components/compare/SpeakerImport.tsx:106`, and add a `provider` arg to `onboardSpeaker()` in `src/api/client.ts:290`. Closes goal #3.
4. **Refresh the UPDATE docs** — merge `parsebuilder-todo.md`, `parseui-current-state-plan.md`, and the Phase-5 slice of `repo-state-cleanup-and-architecture-unification.md` into a single canonical "React + Python-only" plan; trim `react-vite-pivot.md` to just the Python API contract + deletion map; delete or strip `SPEAKERS.md`'s WSL paths.
5. **Close MC-312** — runtime code already has no mock/fixture/fallback data (`ParseUI.tsx:54`). Mark the investigation resolved or confirm with one final grep pass.
