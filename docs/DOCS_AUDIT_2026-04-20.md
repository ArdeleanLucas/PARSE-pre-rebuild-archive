# Docs Audit — 2026-04-20

**Scope:** the 41 pre-existing files that were under `docs/` when this audit was written (6 top-level + 22 in `plans/` + 13 in `plans/oda/`).

**Status note (updated after PR #54 merged):** Stage 1 has already landed on `main`, so the live tree now includes `docs/archive/` and this audit file. Treat the 41-file count as the audited pre-archive set, not the current total file count under `docs/`.

**Project goals driving the audit:**

1. React UI + Python backend (current architecture: `src/` React/TS, `python/` backend).
2. Remove **all** vanilla JS from the project (root `js/` dir, `parse.html`, `compare.html`, `review_tool_dev.html`, legacy launchers).
3. Speaker onboarding must offer a choice between xAI and OpenAI providers.
4. No mock / demo / fixture data in runtime code.

Verdict legend: **KEEP** · **UPDATE** · **OBSOLETE** · **UNCERTAIN**.

**Out of scope:** repo-root `doc/TASK.md` lives outside `docs/` and is not graded here. It should be treated as a separate audit target before anyone uses it as the current source of truth for ParseUI wiring.

---

## Code-state reality check (used to grade each doc)

- **React UI is the live surface.** Root `index.html` bootstraps `src/main.tsx` only. `src/` has all modes (Annotate, Compare, Tags) as React components with Zustand stores, typed API client, Vitest coverage.
- **Legacy vanilla JS is still on disk but orphaned from the React app.** `js/` (25 files, ~984 KB on disk in this audit checkout), `parse.html`, `compare.html`, `review_tool_dev.html` still exist. Only `compare.html` (14 `<script>` refs) and `review_tool_dev.html` (12 refs) load from `js/`. `parse.html` is a self-contained legacy monolith. `vite.config.ts:5–23` ships a `forceSpaCompareRoute` plugin whose comment openly states it exists *because* `compare.html` is still at the repo root.
- **Launchers are split.** `scripts/parse-run.sh` and `run-parse.sh` launch the React stack correctly (Python `server.py` + `npx vite`). `start_parse.sh` and `Start Review Tool.bat` still try to launch a non-existent `python/thesis_server.py` and open `review_tool_dev.html`; both bail with an error on a fresh checkout and each already carries a comment pointing users to the React launcher.
- **No mock data in runtime code.** `grep` for `mock|fixture|demo|stub|fakeData` across `src/` non-test files returns zero hits. `src/ParseUI.tsx:54` explicitly asserts `// No fallback data — workspace must supply real speakers and concepts via /api/config.` Python runtime grep is likewise clean for `mock|fixture|demo|stub`; remaining `sample*` hits are DSP/sample-rate related rather than fixture data.
- **xAI and OpenAI are both registered providers.** `python/ai/provider.py:1091` (`XAIProvider` hitting `https://api.x.ai/v1`, env `XAI_API_KEY`) and `python/ai/provider.py:929` (`OpenAIProvider`). Dispatcher at `provider.py:1254` routes `xai`/`grok`/`x.ai` to `XAIProvider`. LLM/chat auth UI in `src/ParseUI.tsx:243,518,537` and `src/components/annotate/ChatPanel.tsx:57–59` already exposes both providers for key entry.
- **Speaker onboarding is currently provider-agnostic.** `POST /api/onboard/speaker` (`python/server.py:2166–2414`) accepts `speaker_id` + audio WAV + optional CSV. React UI at `src/components/compare/SpeakerImport.tsx:106–159` calls `onboardSpeaker()` (`src/api/client.ts:290–316`). There is **no `provider` parameter** on the call or form, and the current background job only scaffolds annotations / source-index entries. To meet goal #3 the product needs an explicit xAI/OpenAI selector in `SpeakerImport.tsx` plus a clear decision about where that provider choice is consumed or persisted in the onboarding flow.

---

## Top-level `docs/`

| File | Size | Verdict | Reason |
|---|---|---|---|
| [`BUILD_SESSION.md`](archive/BUILD_SESSION.md) | 11 KB | **OBSOLETE** | Wave-based build plan for vanilla-JS modules (`js/annotation-store.js`, `js/annotation-panel.js`, …) and `window.SourceExplorer`→`window.PARSE` namespace migration. All superseded by the React rewrite. |
| [`ONBOARDING_PLAN.md`](ONBOARDING_PLAN.md) | 11 KB | **UPDATE** | Import-wizard design for speaker onboarding (WAV + timestamp CSV + IPA CSV + AI matching). Conceptually aligned with goal #3, but assumes Anthropic Claude as default AI and Ollama fallback — needs rewriting to require xAI/OpenAI selection and to match the current `POST /api/onboard/speaker` contract (not the wizard flow it describes). |
| [`SPEAKERS.md`](SPEAKERS.md) | 7.6 KB | **UPDATE** | Personal thesis data inventory (speaker tiers, WSL `/mnt/c/…` paths, per-speaker transcription CSVs). Useful as a reference for the author's own research data, but the paths are WSL-specific and conflict with `desktop_product_architecture.md`'s portability rules. Move to a research-notes subfolder or strip machine-specific paths. |
| [`desktop_product_architecture.md`](desktop_product_architecture.md) | 18 KB | **UPDATE** | Canonical living plan for Electron + local Python packaging. Architecture direction still correct and lists xAI/OpenAI/Ollama as optional cloud-AI tier (§9.1). However §3 diagram, §16 "Stream 3 — Frontend unification path", and §17 (blockers #2, #7) all reference `parse.html`/`compare.html`/legacy JS as live surface. Refresh: delete vanilla-JS references, promote `src/` React as the sole frontend, add explicit "remove `js/` + `*.html` legacy pages" as a Phase-0 deliverable. |
| [`distribution_readiness_checklist.md`](distribution_readiness_checklist.md) | 7.7 KB | **UPDATE** | Companion checklist to the architecture doc. Mostly goal-aligned, but "Known current blockers" lists Annotate-mode-monolithic-localStorage and legacy launcher references that are stale (Annotate is now React, React launchers exist). Refresh the blocker list; add "`js/`, `parse.html`, `compare.html`, `review_tool_dev.html` removed" and "`start_parse.sh`, `Start Review Tool.bat` removed or rewritten for React" to Gate A / D2. |
| [`runtime_paths_foundation.md`](runtime_paths_foundation.md) | 4.5 KB | **KEEP** | Pure Python helper spec for `python/shared/app_paths.py` + `runtime_config.py`. No vanilla-JS references. Goal-aligned (cross-platform packaging). |

---

## `docs/plans/`

| File | Verdict | Reason |
|---|---|---|
| [`MC-300-parseui-recovery.md`](archive/plans/MC-300-parseui-recovery.md) | **OBSOLETE** | Self-labeled historical; Priority-1 wiring tasks all landed. |
| [`MC-301-parseui-actions-import.md`](archive/plans/MC-301-parseui-actions-import.md) | **OBSOLETE** | Self-labeled historical; landed in PR #18. |
| [`MC-305-branch-cleanup-findings-pr.md`](archive/plans/MC-305-branch-cleanup-findings-pr.md) | **OBSOLETE** | Task-complete; rolling-branch policy it assumes is gone. |
| [`MC-306-parseui-current-state-plan.md`](archive/plans/MC-306-parseui-current-state-plan.md) | **OBSOLETE** | Replacement doc (`parseui-current-state-plan.md`) already exists. |
| [`MC-312-own-data-vs-filler-investigation.md`](plans/MC-312-own-data-vs-filler-investigation.md) | **KEEP** | Mock/fixture/fallback investigation — directly supports goal #4. Checklist still actionable (though `src/ParseUI.tsx:54` suggests most of the hunt is done — close it out once verified). |
| [`actions-job-lifecycle-pr.md`](archive/plans/actions-job-lifecycle-pr.md) | **OBSOLETE** | `useActionJob` hook spec; shipped in PR #38. |
| [`compare-branch-audit.md`](archive/plans/compare-branch-audit.md) | **OBSOLETE** | One-time branch audit; decision acted on. |
| [`contact-lexeme-fetcher.md`](plans/contact-lexeme-fetcher.md) | **KEEP** | Contact-language IPA fetcher using xAI/Grok + Wiktionary/CSV. Python backend + React `ContactLexemePanel`. Aligns with goals #1 and #3; parts still partially implemented. |
| [`generic-comparison-data-pipeline.md`](plans/generic-comparison-data-pipeline.md) | **KEEP** | Provider-registry design extending the contact-lexeme fetcher (xAI Grokipedia, ASJP, CLDF, Wikidata). Core plumbing on `main`, expansion roadmap still relevant. |
| [`github-branch-cleanup-findings-2026-04-10.md`](archive/plans/github-branch-cleanup-findings-2026-04-10.md) | **OBSOLETE** | Self-labeled historical; cleanup done. |
| [`legacy-entrypoint-inventory.md`](plans/legacy-entrypoint-inventory.md) | **KEEP** | Canonical list of every remaining `parse.html`/`compare.html`/`js/`/`localhost:8766` reference. Directly supports goal #2. Highly actionable — use as the checklist for the vanilla-JS removal PR. |
| [`lexibank-setup.md`](plans/lexibank-setup.md) | **KEEP** | Operational setup doc for the Python-side CLDF/CLEF dataset pipeline. No JS surface, no mock data. |
| [`mc-308-audio-pipeline-fix.md`](archive/plans/mc-308-audio-pipeline-fix.md) | **OBSOLETE** | All criteria marked done; shipped PR #43. |
| [`parsebuilder-todo.md`](plans/parsebuilder-todo.md) | **UPDATE** | Active owner TODO, but its gate language and completion notes have drifted from the live `AGENTS.md` workflow. Refresh it against the current goals (vanilla-JS deletion, xAI/OpenAI onboarding, no mock data). |
| [`parseui-current-state-plan.md`](plans/parseui-current-state-plan.md) | **UPDATE** | Best candidate for the canonical React-side plan. Aligned with React+Python. §1 and §3 marked done (PR #33, #38). Refresh with explicit sections for "remove vanilla JS entrypoints" and "xAI/OpenAI onboarding selector"; reconcile C5/C6/C7 vocabulary with the live `AGENTS.md` policy instead of assuming those gates are retired. |
| [`parseui-wiring-todo.md`](archive/plans/parseui-wiring-todo.md) | **OBSOLETE** | Self-labeled archive of the vanilla-JS-era wiring TODO; points to the current-state plan. |
| [`pr38-dispatch-specs.md`](archive/plans/pr38-dispatch-specs.md) | **OBSOLETE** | Implementation brief for landed PR #38. |
| [`pr38-role-split.md`](archive/plans/pr38-role-split.md) | **OBSOLETE** | Agent-handoff coordination for landed PR #38. |
| [`react-vite-pivot.md`](plans/react-vite-pivot.md) | **UPDATE** | 47 KB foundational plan for the JS→React pivot. Load-bearing technical content (Python API contract + `js/`→React migration map) is still useful but phase tracker is stale. Trim to: (a) Python API contract as authoritative reference, (b) `js/`→React migration map as the deletion checklist. Drop branch/phase churn. |
| [`repo-cleanup-preflight.md`](archive/plans/repo-cleanup-preflight.md) | **OBSOLETE** | One-time 2026-04-09 branch snapshot; list now fully pruned. |
| [`repo-state-cleanup-and-architecture-unification.md`](plans/repo-state-cleanup-and-architecture-unification.md) | **UPDATE** | Phase-5 task 5.1/5.2 is *exactly* the vanilla-JS deletion + Python-serves-`dist/` cutover goal #2 needs. Phases 0–4 and 6 are largely done. Strip to the Phase-5 plan and reconcile any C5/C6 wording with the live `AGENTS.md` policy instead of assuming those gates are gone. |
| [`worktree-setup.md`](plans/worktree-setup.md) | **UPDATE** | Multi-agent worktree ops doc. Still useful but references stale branch names and the uppercase archival clone. Trim historical-notes section; confirm the current agent roster. |

---

## `docs/plans/oda/`

"ODA" was a named agent persona owning Track B (Compare Mode) of a dual-agent React+Vite pivot. `oda-core.md:93` logs a 2026-04-08 audit that rebuilt Oda's work from scratch, and every B-component it scoped (`ConceptTable`, `CognateControls`, `BorrowingPanel`, `TagManager`, `EnrichmentsPanel`, `SpeakerImport`, `useExport`, `useComputeJob`, `CompareMode`) exists in `src/components/compare/` and `src/hooks/` today. The entire track is landed.

| File | Verdict | Reason |
|---|---|---|
| [`b1-concept-table.md`](archive/plans/oda/b1-concept-table.md) | **OBSOLETE** | `src/components/compare/ConceptTable.tsx` landed. |
| [`b2-cognate-controls.md`](archive/plans/oda/b2-cognate-controls.md) | **OBSOLETE** | `CognateControls.tsx` landed. |
| [`b3-borrowing-panel.md`](archive/plans/oda/b3-borrowing-panel.md) | **OBSOLETE** | `BorrowingPanel.tsx` landed. |
| [`b4-tag-manager.md`](archive/plans/oda/b4-tag-manager.md) | **OBSOLETE** | `TagManager.tsx` landed. |
| [`b5-enrichments-panel.md`](archive/plans/oda/b5-enrichments-panel.md) | **OBSOLETE** | `EnrichmentsPanel.tsx` landed. |
| [`b6-speaker-import.md`](plans/oda/b6-speaker-import.md) | **UPDATE** | Component exists (`SpeakerImport.tsx`), but the real flow is WAV+CSV upload to `/api/onboard/speaker`, not the JSON state-machine this spec describes. Drift. Either archive or rewrite to reflect the real onboarding contract (and add the xAI/OpenAI provider selector goal #3 requires). |
| [`b7-export.md`](archive/plans/oda/b7-export.md) | **OBSOLETE** | `useExport.ts` landed; LingPy/NEXUS endpoints wired in `client.ts`. |
| [`b8-compute-job.md`](archive/plans/oda/b8-compute-job.md) | **OBSOLETE** | `useComputeJob.ts` landed. |
| [`b9-compare-mode.md`](archive/plans/oda/b9-compare-mode.md) | **OBSOLETE** | `CompareMode.tsx` assembled per checklist. |
| [`coordination.md`](archive/plans/oda/coordination.md) | **OBSOLETE** | Oda↔ParseBuilder handoff protocol; Track B audit already closed it. |
| [`oda-core.md`](archive/plans/oda/oda-core.md) | **OBSOLETE** | Self-labels its branch notes as historical; build status records completion. |
| [`phase-0.md`](archive/plans/oda/phase-0.md) | **OBSOLETE** | Scaffold gate long passed. |
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

## Execution plan

Five stages total. **Stage 1 has already landed via PR #54** (`docs/archive-obsolete-2026-04-20`), so the remaining execution work is Stages 2–5. The order below keeps risky deletions behind provider-selection work and the current PARSE release gates.

This PR still only adds the audit + living execution plan. Since opening, Stage 1 has already been executed on `main`; the remaining stages are intentionally separate follow-up PRs.

### Preflight — legacy-entrypoint inventory (evidence for Stage 3)

The table below inventories the main repo files still implicated in legacy entrypoints. Treat the list as authoritative; the exact grep count shifts as archival/docs-cleanup work lands.

| File | Why it matters | Action |
|---|---|---|
| `AGENTS.md:114` | Policy language about React vs legacy entrypoints | Remove "legacy entrypoint" allowance |
| `README.md:13,21,33,71,261–288` | Documents legacy fallback URLs + tree layout | Rewrite — React is sole frontend |
| `desktop/main.js:7,101`, `desktop/dev-launch.js:9,56`, `desktop/README.md:16,56` | Electron shell defaults to `http://127.0.0.1:8766/parse.html` | Repoint to React dev server / built `dist/` |
| `python/server.py:3100–3105` | Startup banner advertises `/parse.html` and `/compare.html` URLs | Replace with React URLs (`:5173` in dev, `:8766/` in prod once `dist/` is served) |
| `python/test_server_normalize_safety.py:63` | Asserts banner contains `compare.html` | Update assertion |
| `vite.config.ts:5–23` | `forceSpaCompareRoute` plugin masks `compare.html` | Delete plugin + import |
| `start_parse.sh`, `Start Review Tool.bat` | Broken legacy launchers | Delete |
| `js/compare/compare.js`, `js/concept-table.js` | Self-references inside `js/` | Deleted with the directory |
| `docs/archive/BUILD_SESSION.md`, `desktop_product_architecture.md`, `distribution_readiness_checklist.md`, `plans/legacy-entrypoint-inventory.md`, `plans/react-vite-pivot.md`, `docs/archive/plans/repo-cleanup-preflight.md`, `plans/repo-state-cleanup-and-architecture-unification.md` | Documentation | Stage 1 archived the OBSOLETE ones; Stage 4 refreshes the UPDATE ones |

This list supersedes the stale copy in `plans/legacy-entrypoint-inventory.md`.

---

### Stage 1 — Archive obsolete docs (completed in PR #54)

**Branch:** `docs/archive-obsolete-2026-04-20`
**Goal:** Move the 24 OBSOLETE files to `docs/archive/` so the surviving plans are easier to find and trust.

**Status:** merged to `main` in PR #54 (merge commit `187a076`). Leave the plan here as a record because later stages now depend on the `docs/archive/` layout that exists on `main`.

**Structure:**

```text
docs/archive/
  BUILD_SESSION.md
  plans/
    MC-300-parseui-recovery.md
    MC-301-parseui-actions-import.md
    MC-305-branch-cleanup-findings-pr.md
    MC-306-parseui-current-state-plan.md
    actions-job-lifecycle-pr.md
    compare-branch-audit.md
    github-branch-cleanup-findings-2026-04-10.md
    mc-308-audio-pipeline-fix.md
    parseui-wiring-todo.md
    pr38-dispatch-specs.md
    pr38-role-split.md
    repo-cleanup-preflight.md
    oda/              # archived in PR #54: b1–b5, b7–b9, coordination, oda-core, phase-0
                      # (`b6-speaker-import.md` stays active; `rules.md` handled in Stage 4)
```

**Steps:**

1. `git mv` each of the 24 files into `docs/archive/` preserving subfolder layout.
2. Add `docs/archive/README.md` explaining: "Archived 2026-04-20 based on [`../DOCS_AUDIT_2026-04-20.md`](../DOCS_AUDIT_2026-04-20.md). These documents describe landed work, completed cleanups, or the pre-React vanilla-JS architecture. Preserved for history. Do not use as plans."
3. Grep for any link to a moved file from a non-archived doc — there are a few (for example `repo-state-cleanup-and-architecture-unification.md` references `repo-cleanup-preflight.md`). Update those references to the new `../archive/...` path.
4. No code changes. No tests to run.

**Risk:** minimal — git history is unaffected by `git mv`. If someone cites an old URL, it now 404s; add a line in the main README pointing to `docs/archive/` if external links exist.

**Exit criteria:** all 24 Stage-1 files in `docs/archive/`; `docs/plans/oda/b6-speaker-import.md` and `docs/plans/oda/rules.md` still present for later handling; CI green.

---

### Stage 2 — xAI/OpenAI speaker-onboarding selector (backend + frontend + tests)

**Branch:** `feat/onboard-speaker-provider-selector`
**Goal:** Close project goal #3. The speaker-onboarding UI/contract accepts an explicit `provider` choice (`xai` | `openai`) and records or validates that choice in a way that future provider-dependent onboarding steps can honor.

**Backend changes (`python/`):**

1. `python/server.py:2315` `_api_post_onboard_speaker` — read `provider` from the multipart form:
   - Accept values: `"xai"`, `"openai"`.
   - If absent → `400 {"error":"provider is required","allowed":["xai","openai"]}`.
   - If unknown → `400 {"error":"unsupported provider","allowed":[...]}`.
   - If the corresponding env key is missing (`XAI_API_KEY` for `xai`, `OPENAI_API_KEY` for `openai`) → `400 {"error":"provider not configured","provider":"xai"}` so the UI can route the user to the auth flow.
2. `python/server.py:1633` `_run_onboard_speaker_job` — extend the job payload/result to carry `provider: str` even though the current implementation is scaffolding-only. That prevents future provider-dependent onboarding steps from inferring global auth state implicitly.
3. `python/ai/provider.py` — add a small helper `get_provider_for(name: str, config)` that returns the `OpenAIProvider` or `XAIProvider` instance for `name`, so the onboarding job can request one by name without touching global state.
4. Tests in `python/test_server.py` (or a new `python/test_onboard_speaker.py`):
   - missing `provider` → 400
   - unknown `provider` → 400
   - valid `xai` + no `XAI_API_KEY` → 400 with `provider` in payload
   - valid `openai` + key set → job starts, returns `job_id`
5. `python/server.py:2166` endpoint doc string + OpenAPI-style comment listing the new field.

**Frontend changes (`src/`):**

1. `src/api/client.ts:290` `onboardSpeaker` — add `provider: 'xai' | 'openai'` parameter, append to `FormData`. Update return type if error shape changes.
2. `src/components/compare/SpeakerImport.tsx:106` — add a provider radio group above the audio field. Pre-select the currently-authed provider from the config store. Disable a radio if that provider's key is not present; show an "Authorize xAI/OpenAI in Settings" inline hint with a link to the auth flow (`ParseUI.tsx:243,518,537`).
3. Wire the selected provider into the `onboardSpeaker` call (form submission).
4. Update `src/components/compare/SpeakerImport.test.tsx`:
   - renders both radios
   - defaults to authed provider
   - disables unauthed providers with inline hint
   - submits `provider` field in FormData

**Current gate note:** `AGENTS.md` still marks `src/components/compare/*` as stable / do-not-touch pre-C6. Treat the `SpeakerImport.tsx` UI slice as gated behind an explicit Lucas exception (or a later gate change). The backend/client contract work can still be prepared independently.

**Docs:**

- Update `docs/ONBOARDING_PLAN.md` §"AI provider" open question to resolved requirement: "user must choose xAI or OpenAI at import time; no implicit default; Ollama deferred". Covered by Stage 4 but flag in PR description.

**Risk:** low — additive field on an existing endpoint. Backwards-compat note: any existing automated caller must add `provider`. No such callers exist outside the React UI (grepped).

**Exit criteria:** new tests green; manual smoke in Vite dev (upload a real WAV + CSV with each provider selected, confirm the selected provider is captured/validated as intended by the updated contract). `npm run test` + `npm run test:api:live` + `python3 -m pytest python/` all pass.

---

### Stage 3 — Vanilla-JS deletion (breaking change for anyone using legacy URLs)

**Branch:** `chore/remove-vanilla-js`
**Goal:** Close project goal #2. Only `src/` React + `python/` backend remain as the product surface.

**Preflight gate (must all pass before deletion):**

- **Lucas clears C5 + C6 explicitly.** Current `AGENTS.md` blocks C7 cleanup / legacy deletion until those manual gates are passed.
- Stage 1 merged (archived docs reference clean legacy inventory).
- Stage 2 merged (onboarding tested against the React UI as the only frontend).
- A recent `scripts/parse-run.sh` smoke test passes from a clean checkout — Annotate, Compare, Tags modes all load, speaker onboarding works, compute jobs work.
- `npm run test` + `npm run test:api` pass on `main`.

**Deletions:**

```
git rm -r js/
git rm parse.html compare.html review_tool_dev.html
git rm start_parse.sh "Start Review Tool.bat"
```

**Code edits:**

1. `vite.config.ts:5–23` — delete the `forceSpaCompareRoute` plugin and its import. Verify `/compare` still routes to the React app via `react-router-dom` (it does, via `App.tsx` + `BrowserRouter`).
2. `python/server.py:3100–3105` — rewrite startup banner:
   - Dev: `React UI (dev): http://localhost:5173/` (managed by `scripts/parse-run.sh`).
   - Prod (when `dist/` is served by Python): `PARSE: http://localhost:{PORT}/`.
3. `python/test_server_normalize_safety.py:63` — update assertion: banner no longer contains `compare.html`. Replace with the new URL format or drop the assertion if it's only about banner content.
4. `desktop/main.js:7`, `desktop/dev-launch.js:9` — change `DEFAULT_APP_URL` to `http://127.0.0.1:5173/` (dev) or leave configurable via `--url`.
5. `desktop/main.js:101`, `desktop/README.md:16,56`, `desktop/dev-launch.js:56` — strip legacy-fallback language.
6. `AGENTS.md:114` — remove the "Non-destructive documentation/policy clarification about React vs legacy entrypoints" carve-out.
7. `README.md` — rewrite the frontend architecture paragraph, remove "Legacy fallback UI" URLs, remove `parse.html`/`compare.html` from the tree listing, remove the "pre-C7" language anywhere it appears.
8. `scripts/parse-run.sh` and `run-parse.sh` — audit for any legacy references (should be none based on earlier grep).

**Python serves `dist/` (optional, same PR):**

If the plan is for prod to run headless without Vite, add a `python/server.py` route that serves `dist/` at `/` when it exists. Otherwise defer to a follow-up.

**Risk:** **medium.** Breaks anyone relying on `http://localhost:8766/parse.html` URLs (the README currently advertises these). Mitigations:

- Prominent changelog note in the PR body.
- The Electron shell and docs get updated in the same PR.
- Consider a deprecation release (one version with `parse.html` returning a 410 Gone + "open localhost:5173 or built `dist/`" HTML) before hard-deleting. Only do this if external users are known to exist; for a single-owner repo, skip.

**Exit criteria:**

- `find . -name "parse.html" -o -name "compare.html" -o -name "review_tool_dev.html"` returns only `docs/archive/…`.
- `rg "forceSpaCompareRoute" .` returns 0 hits.
- `rg "parse\.html|compare\.html|review_tool_dev\.html" -l --glob '!docs/archive/**' --glob '!docs/DOCS_AUDIT*.md'` returns 0 hits.
- `ls js/` → No such file or directory.
- `npm run test` + `npm run test:api` + `python3 -m pytest python/` pass.
- `scripts/parse-run.sh` smoke test against all three modes + onboarding.

---

### Stage 4 — Refresh UPDATE docs (docs-only, follows Stages 1–3 outcomes)

**Branch:** `docs/refresh-update-plans-2026-04-20`
**Goal:** Rewrite the 11 UPDATE docs so they match the post-Stage-3 world.

| File | Edit plan |
|---|---|
| `docs/ONBOARDING_PLAN.md` | §"AI provider" open question → resolved requirement ("user must choose xAI or OpenAI at onboarding; Ollama out of scope for now"). Update Task A–D instructions to be provider-agnostic strings (model-name only). Remove Claude-as-default mentions. Point to the new `SpeakerImport.tsx` + `/api/onboard/speaker` contract from Stage 2. |
| `docs/SPEAKERS.md` | Move to `docs/research-notes/SPEAKERS.md` (personal thesis inventory, not a project plan). Strip §"Key Paths (WSL)" and any `/mnt/c/...` references. Add a note at the top: "Personal research data inventory — not a project plan." |
| `docs/desktop_product_architecture.md` | §3 diagram: remove "existing JS modules" line from the renderer box. §16 Stream 3 "Frontend unification path": mark complete, remove Annotate/Compare-divergence language. §17 blockers: strike #2 (Annotate monolithic — no longer true) and #7 (CDN — verify with `rg unpkg src/`) after Stage 3 lands. Add a "Decision log" entry for Stage 3 vanilla-JS removal. |
| `docs/distribution_readiness_checklist.md` | "Known current blockers" list: strike the items resolved by Stages 2+3 (legacy launcher refs, Annotate monolithic, project save contract if that's done, CDN dependency). Add a new D2 item: "Legacy vanilla-JS entrypoints removed" with a `[x]` once Stage 3 merges. |
| `docs/plans/parsebuilder-todo.md` | Either delete (if fully subsumed by `parseui-current-state-plan.md`) or rewrite as a minimal "current blocked items" list. Reconcile C5/C6/C7 language with the then-current `AGENTS.md` policy instead of assuming those gates are retired. Drop stale completion dates. |
| `docs/plans/parseui-current-state-plan.md` | This becomes the canonical React-side plan. Section updates: (1) remove sections now marked done (§1, §3); (2) add an explicit "Remove vanilla JS entrypoints" section with a link to Stage 3's PR; (3) add an "xAI/OpenAI onboarding selector" section referencing Stage 2; (4) keep or explicitly supersede C5/C6/C7 vocabulary based on the live `AGENTS.md`, rather than deleting it by default. |
| `docs/plans/react-vite-pivot.md` | Shrink from 47 KB to ≤10 KB: keep only (a) the Python API contract table (authoritative reference), (b) the `js/` → React migration map as historical context (once deleted, it's record-keeping not a plan). Everything else — phase tracker, branch churn, date entries — deleted. |
| `docs/plans/repo-state-cleanup-and-architecture-unification.md` | Strip to just the Phase 5 slice (vanilla-JS deletion + Python-serves-`dist/` cutover). After Stage 3 merges, mark Phase 5 complete and consider archiving. Phases 0–4 and 6 are already done — note that and remove their step lists. Reconcile any C5/C6 wording with the live `AGENTS.md` policy instead of assuming those gates are gone. |
| `docs/plans/worktree-setup.md` | Trim historical-notes section. Confirm the current agent roster (ParseBuilder / parse-gpt references are stale). Keep the lowercase-clone + branch-from-`origin/main` ops, drop the rest. |
| `docs/plans/oda/rules.md` | Extract the still-valid rules (Zustand-only, strict TS, no inline styles, no `window.PARSE`, no bare `fetch`) into `AGENTS.md` under a "Frontend rules" heading. Then `git mv` the file to `docs/archive/plans/oda/rules.md` so the entire `oda/` folder is archived. |
| `docs/plans/MC-312-own-data-vs-filler-investigation.md` | Closed as "no further action needed" — see Stage 5. |

**Risk:** low — docs-only. Main risk is stale cross-links; grep every moved/renamed doc before merging.

**Exit criteria:** each UPDATE doc reflects post-Stage-3 reality, no stale references to deleted files remain outside `docs/archive/`, and any surviving C5/C6/C7 language either matches the live `AGENTS.md` policy or is explicitly superseded by an updated policy document.

---

### Stage 5 — Close out MC-312 (docs-only confirmation)

**Branch:** `docs/close-mc-312`
**Goal:** Close goal #4 loop. Record the final evidence that no mock/fixture/fallback data remains.

**Steps:**

1. After Stage 3 merges, run a final audit grep from a clean checkout:
   ```bash
   rg -i 'mock|fixture|fake|stub|demo|sample(?!_rate|Rate)' src/ --glob '!**/*.test.*' --glob '!**/__tests__/**'
   rg -i '"(sample|mock|demo|fake|stub)"' python/ --glob '!**/test_*.py' --glob '!**/*_test.py'
   ```
   Expected output: none (or only audio `sample_rate` matches, which are DSP, not mock).
2. In `docs/plans/MC-312-own-data-vs-filler-investigation.md`, append a "Closed 2026-04-20" section with the grep commands, the exit codes, and the link to `ParseUI.tsx:54`'s explicit assertion.
3. `git mv docs/plans/MC-312-own-data-vs-filler-investigation.md docs/archive/plans/`.

**Risk:** minimal.

**Exit criteria:** MC-312 archived with closing evidence.

---

## Ordering and dependency graph

```
Stage 1 (archived in PR #54) ──┐
                                ├─→ Stage 4 (refresh UPDATE docs)
Stage 2 (provider selector) ────┤
                                │
Stage 3 (delete vanilla JS; blocked until C5+C6) ──┘→ Stage 5 (close MC-312)
```

- Stage 1 is already complete on `main`.
- Stage 2 can run now only if Lucas explicitly blesses the temporary `src/components/compare/*` exception (or moves that UI slice behind a later gate).
- Stage 3 depends on Stage 2 **and** explicit C5+C6 clearance because current `AGENTS.md` blocks C7 cleanup/deletion until those manual gates pass.
- Stage 4 depends on Stages 1–3 (rewrites need the post-deletion reality) and should preserve any still-active gate language unless repo policy changes first.
- Stage 5 depends on Stage 3 (final grep must be over the post-deletion tree).

**Estimated effort (single-operator):**

| Stage | Effort | Risk |
|---|---|---|
| 1 | 1 h | Minimal |
| 2 | 3–4 h | Low |
| 3 | 2–3 h | Medium |
| 4 | 3–4 h | Low |
| 5 | 15 min | Minimal |

**Total:** ~1 focused day of work across 5 PRs.
