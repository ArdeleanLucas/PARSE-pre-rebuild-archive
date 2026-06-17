# MC-321 — Mand01/Qasr01 batch pipeline audit

> **For Hermes:** Use `systematic-debugging` for reproduction and evidence gathering. Use `parse-pr-workflow` for branch/PR hygiene. This document is both a postmortem and an implementation-ready fix plan.

## Goal

Explain why **Mand01** and **Qasr01** appeared to fail in the 2026-04-25 batch report, identify the real backend/runtime state, isolate the distinct bugs involved, and define the smallest durable fixes.

## Executive summary

The batch report mixed together **two different failures**:

1. **Frontend/dev-runtime connectivity failure** during the batch run
   - **Mand01** was marked errored because the UI could no longer poll `POST /api/compute/full_pipeline/status`.
   - **Qasr01** was marked errored because the next `POST /api/compute/full_pipeline` never reached the backend.
   - The **Python backend was alive** the whole time; the missing component was the **Vite dev server / `/api` proxy** on port `5173`.

2. **Backend IPA forced-alignment failure** affecting the batch generally
   - Earlier speakers and the eventually-completed **Mand01** all failed at the IPA step with:
     `RuntimeError: Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called`
   - Root cause: `python/ai/forced_align.py` calls `torch.set_num_interop_threads(1)` inside `Aligner.load()` on CPU, after other parallel work has already started in **thread compute mode**.

### Key conclusion

**Mand01 was not truly unprocessed.** It continued on the backend and later completed with:
- `normalize`: skipped
- `stt`: ok
- `ortho`: ok
- `ipa`: error (interop-thread bug)

**Qasr01 never started**, because the frontend lost API reachability before its start request could be proxied.

---

## Evidence corpus

### 1) User-supplied batch report (downloaded JSON)

Source file:
- `/mnt/c/Users/Lucas/Desktop/parse/parse-batch-report-2026-04-25T12_51_25.564Z.json`

Relevant lines:

```json
{
  "speaker": "Mand01",
  "status": "error",
  "error": "Could not reach the PARSE API for POST /api/compute/full_pipeline/status. Check that the Python server is running on http://127.0.0.1:8766 and that the Vite /api proxy is active.",
  "result": null
},
{
  "speaker": "Qasr01",
  "status": "error",
  "error": "Could not reach the PARSE API for POST /api/compute/full_pipeline. Check that the Python server is running on http://127.0.0.1:8766 and that the Vite /api proxy is active.",
  "result": null
}
```

Interpretation:
- Mand01 failed on **poll** (`/status`) — meaning the job may already have been launched.
- Qasr01 failed on **start** (`/full_pipeline`) — meaning it likely never got queued.

### 2) Live backend state at investigation time

Process state:

```bash
$ ps -p 1397 -o pid=,cmd=
1397 /usr/bin/python3 -u /home/lucas/gh/ardeleanlucas/parse/python/server.py --compute-mode=thread
```

Environment on the live server process:

```bash
PARSE_AI_CONFIG=/home/lucas/parse-workspace/config/ai_config.json
PARSE_EXTERNAL_READ_ROOTS=*
PARSE_WORKSPACE_ROOT=/home/lucas/parse-workspace
PARSE_PULL_MODE=reset
PARSE_CHAT_DOCS_ROOT=/home/lucas/parse-workspace
PARSE_ROOT=/home/lucas/gh/ardeleanlucas/parse
PARSE_CHAT_READ_ONLY=0
```

Worker health endpoint:

```bash
$ curl -s http://127.0.0.1:8766/api/worker/status
{"mode": "thread", "alive": null, "message": "Persistent worker mode is not active"}
```

Interpretation:
- Backend was healthy enough to answer requests.
- Runtime was explicitly `--compute-mode=thread`, which matters for the IPA failure.

### 3) Direct backend vs Vite proxy connectivity

Observed during audit:

```bash
$ curl -s -o /dev/null -w '%{http_code}\n' \
    -X POST http://127.0.0.1:8766/api/compute/full_pipeline/status \
    -H 'Content-Type: application/json' \
    -d '{"job_id":"81e16497-d71d-4c5b-98e1-6c7a9b5764fd"}'
200

$ curl -s -o /dev/null -w '%{http_code}\n' \
    -X POST http://127.0.0.1:5173/api/compute/full_pipeline/status \
    -H 'Content-Type: application/json' \
    -d '{"job_id":"81e16497-d71d-4c5b-98e1-6c7a9b5764fd"}'
000
```

There was also **no live Vite process** at the time of inspection, while port `8766` was listening and `5173` was not.

Interpretation:
- The backend path was available.
- The dev-UI path (`Vite -> /api proxy -> backend`) was not.
- The exact frontend error string was therefore truthful about the symptom, but misleading as a speaker-level batch outcome.

### 4) Backend compute checkpoint log

Source file:
- `/tmp/parse_compute_checkpoint.log`

Mand01 launch evidence:

```text
2026-04-25T11:50:11.117039Z  ThreadPoolExecutor-0_0  1397  LAUNCH.thread   job_id=81e16497-d71d-4c5b-98e1-6c7a9b5764fd  compute_type=full_pipeline  mode=thread
2026-04-25T11:50:11.118624Z  Thread-8 (_run_compute_job)  1397  COMPUTE.entry     job_id=81e16497-d71d-4c5b-98e1-6c7a9b5764fd  compute_type=full_pipeline
2026-04-25T11:50:11.119934Z  Thread-8 (_run_compute_job)  1397  COMPUTE.dispatch  job_id=81e16497-d71d-4c5b-98e1-6c7a9b5764fd  normalized=full_pipeline
```

Notably absent:
- **No `Qasr01` entries** in the checkpoint log.

Interpretation:
- Mand01 definitely started backend-side.
- Qasr01 never reached `_launch_compute_runner` / `_run_compute_job`.

### 5) Live Mand01 job status after the report had already said "error"

Direct backend status result for Mand01 job id `81e16497-d71d-4c5b-98e1-6c7a9b5764fd` eventually returned:

```json
{
  "jobId": "81e16497-d71d-4c5b-98e1-6c7a9b5764fd",
  "status": "complete",
  "progress": 100.0,
  "result": {
    "speaker": "Mand01",
    "steps_run": ["normalize", "stt", "ortho", "ipa"],
    "results": {
      "normalize": {
        "status": "skipped",
        "reason": "normalized output already exists; overwrite=False",
        "path": "audio/working/Mand01/Mandali_M_1900_01.wav"
      },
      "stt": { "status": "ok", "segments": 206, "done": true },
      "ortho": {
        "status": "ok",
        "speaker": "Mand01",
        "filled": 909,
        "ortho_words": 10705,
        "refined_lexemes": 0,
        "refine_lexemes_enabled": false,
        "skipped": false,
        "replaced_existing": true,
        "audio_path": "/home/lucas/parse-workspace/audio/working/Mand01/Mandali_M_1900_01.wav",
        "total": 909
      },
      "ipa": {
        "status": "error",
        "error": "Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called"
      }
    },
    "summary": { "ok": 2, "skipped": 1, "error": 1 }
  },
  "type": "compute:full_pipeline",
  "message": "Compute complete",
  "done": true,
  "success": true
}
```

Interpretation:
- The batch report’s `Mand01` row was stale/wrong at the speaker-outcome level.
- The backend finished the run and recorded a structured step-level failure.

---

## Code audit

## A. Frontend connectivity/error-shaping path

### `src/api/client.ts`

```ts
function networkError(path: string, options: RequestInit | undefined, error: unknown): Error {
  const message = error instanceof Error ? error.message : String(error ?? "Unknown fetch error");
  if (/failed to fetch|networkerror/i.test(message)) {
    return new Error(
      `Could not reach the PARSE API for ${options?.method ?? "GET"} ${path}. `
      + `Check that the Python server is running on http://127.0.0.1:8766 and that the Vite /api proxy is active.`,
    );
  }
  return error instanceof Error ? error : new Error(message);
}
```

This code is fine as a **transport error mapper**, but once it bubbles into batch state it becomes indistinguishable from a genuine speaker-level failure.

### `src/hooks/useBatchPipelineJob.ts`

Start path:

```ts
const job = await startCompute("full_pipeline", body);
jobId = String(job.job_id || "").trim();
```

Poll path:

```ts
try {
  poll = await pollCompute("full_pipeline", jobId);
} catch (error) {
  pollErrored = true;
  pollErrorMessage = toErrorMessage(error, "Pipeline poll failed");
  break;
}
```

Outcome shaping after poll failure:

```ts
if (pollErrored) {
  nextOutcomes[i] = {
    ...nextOutcomes[i],
    status: "error",
    error: pollErrorMessage,
    result: pollResult,
  };
}
```

#### Audit finding

This is the crucial UX/data-integrity bug.

If a speaker job **starts successfully** and later the client loses connectivity during polling:
- the hook already knows `jobId`
- but it **throws away that recoverable state**
- and writes a terminal `status: "error"` outcome with `result: null`

That makes a **transport interruption look like a true speaker failure**, even though the backend may still be running or may already have completed.

### `src/components/shared/BatchReportModal.tsx`

Type comments:

```ts
/** Whole-speaker error (e.g. network failure before the pipeline job even started). */
error: string | null;
result: PipelineRunResult | null;
```

And later:

```ts
const isWholeSpeakerError =
  outcome.status === "error" && outcome.result === null;
```

#### Audit finding

The component assumes `status === "error" && result === null` means the speaker never started.
That assumption is false for the Mand01 case:
- speaker **did** start
- polling failed later
- backend finished anyway
- report JSON still serialized `result: null`

The UI model therefore collapses **at least two distinct states** into one:
1. **start failed / never queued**
2. **queued, but client lost contact**

### `src/components/shared/BatchReportModal.tsx` download path

```ts
const payload = {
  generated_at: new Date().toISOString(),
  steps_run: stepsRun,
  outcomes,
};
```

#### Audit finding

The downloaded JSON is purely a snapshot of current client memory. It has no reconciliation step against live backend job state before export. If the UI lost contact, the report preserves that stale/errorful client view forever.

---

## B. Backend IPA forced-alignment failure

### `python/server.py`

```py
_IPA_ALIGNER: Any = None

def _get_ipa_aligner() -> Any:
    global _IPA_ALIGNER
    if _IPA_ALIGNER is not None:
        _compute_checkpoint("ALIGNER.cached")
        return _IPA_ALIGNER
    ...
    _IPA_ALIGNER = Aligner.load(device=_ipa_device)
```

### `python/ai/forced_align.py`

```py
resolved_device = resolve_device(device)

if resolved_device == "cpu":
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
```

#### Audit finding

This code is safe only if it runs **before** PyTorch parallel work has started. In the live deployment:
- server runs in `--compute-mode=thread`
- batch work has already started other torch/parallel activity before IPA aligner first-load
- the first CPU aligner load then attempts `torch.set_num_interop_threads(1)` too late
- PyTorch raises:

```text
RuntimeError: Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called
```

This failure was visible in:
- earlier rows of the same batch report (Fail01, Kalh01, Khan01-04)
- Mand01 once its backend job completed
- checkpoint log entries like:

```text
ALIGNER.load_error ... exc=Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called
```

### Runtime mode evidence

`/api/worker/status` returned:

```json
{"mode": "thread", "alive": null, "message": "Persistent worker mode is not active"}
```

That matters because the repo already contains a persistent-worker architecture intended to preload/reuse the aligner, but the live process was **not using it**.

---

## Root-cause analysis

## Root cause 1 — dev-runtime connectivity loss (Mand01/Qasr01 reporting failure)

### What happened

1. Batch ran successfully through earlier speakers.
2. Mand01 was launched and got a real backend job id.
3. During Mand01 polling, the UI could no longer reach `/api/...` through Vite.
4. The hook converted that into a terminal speaker error with no result.
5. The next speaker, Qasr01, failed even earlier — the start call itself never reached the backend.
6. The user exported the client-side report in that stale state.

### Proven by

- Mand01 had a backend job id and launch log.
- Qasr01 had no backend launch evidence.
- `:8766` answered live status calls.
- `:5173` did not.

### Why this is a product bug, not just "ops"

Even if the immediate cause was a dead dev server, the **product behavior is still wrong**:
- a recoverable/disconnected state is recorded as a terminal speaker failure
- the report exports stale client memory as if it were ground truth
- the UI loses the `jobId` needed for reattachment

## Root cause 2 — IPA aligner thread-init bug

### What happened

The first IPA aligner load in thread mode attempted to set PyTorch interop threads after parallel work had already started.

### Proven by

- traceback in batch report
- checkpoint log `ALIGNER.load_error`
- exact offending line in `forced_align.py`

### Why this is a code bug

The current implementation assumes it can safely call `torch.set_num_interop_threads(1)` during lazy aligner load. In a long-lived server with earlier torch work, that assumption is false.

---

## Impact assessment

### User-visible impact

- False conclusion that Mand01 was wholly unprocessed.
- Qasr01 skipped entirely.
- Batch report became a misleading forensic artifact.
- Rerun decisions based on that report risk unnecessary recomputation.

### Data/state impact

Mand01 workspace artifacts were updated despite the report saying "error":
- `coarse_transcripts/Mand01.json` updated during this run
- ORTH output filled `909` concepts/intervals according to backend status

Qasr01 artifacts were not updated by this incident because it never started.

### Operational impact

- Dev runtime fragility: Vite absence kills the whole UI transport layer.
- Thread mode leaves IPA vulnerable to this aligner-init timing issue.

---

## Test coverage audit

### Existing coverage found

`src/hooks/__tests__/useBatchPipelineJob.test.ts` covers:
- sequential execution
- per-speaker backend error continuation
- `startCompute` rejection continuation
- progress updates
- cancel semantics
- `stepsBySpeaker` behavior

### Missing coverage

No test currently covers:
1. **start succeeds, poll fails, backend job id exists**
2. outcome needing **reattach/reconcile** rather than terminal error
3. report download needing **job metadata** / reconcilable state
4. backend regression around **late `set_num_interop_threads` calls**

This gap explains how the Mand01 failure mode escaped the current suite.

---

## Recommended fixes

## Fix 1 — preserve job identity on poll/network failure

### Objective

If `startCompute()` succeeded and polling later fails, preserve enough metadata to reattach or at minimum report a distinct non-terminal state.

### Suggested shape

Extend the batch outcome model from:

```ts
{
  speaker,
  status: "error",
  error,
  result: null,
}
```

To something like:

```ts
{
  speaker,
  status: "disconnected", // or "lost_contact"
  error,
  result: null,
  jobId,
  phase: "poll",
}
```

At minimum, add:
- `jobId?: string`
- `errorPhase?: "start" | "poll"`

### File targets
- `src/hooks/useBatchPipelineJob.ts`
- `src/components/shared/BatchReportModal.tsx`
- `src/hooks/__tests__/useBatchPipelineJob.test.ts`
- `src/components/shared/__tests__/BatchReportModal.test.tsx`

### Acceptance criteria
- Mand01-type failure renders as **started, lost contact** rather than generic speaker error.
- Exported JSON includes the backend `jobId` if known.
- UI can clearly distinguish:
  - never started
  - started but disconnected
  - completed with step-level error

## Fix 2 — add reconciliation before exporting batch report

### Objective

Before downloading the report, reconcile any outcomes with known `jobId`s by polling live status once.

### Suggested behavior

For each outcome with `jobId` and a non-terminal/disconnected state:
1. call `pollCompute("full_pipeline", jobId)`
2. if found complete/error, replace the stale client outcome with live status/result
3. then serialize JSON

### File targets
- `src/components/shared/BatchReportModal.tsx`
- maybe helper in `src/api/client.ts`

### Acceptance criteria
- A report downloaded after a transient UI disconnect no longer freezes a stale false-negative if the backend job is still available.

## Fix 3 — preflight transport health between speakers

### Objective

Fail fast and clearly when the UI transport has died, instead of pretending the next speaker had a content/pipeline failure.

### Suggested behavior

Before launching each next speaker, optionally probe a cheap endpoint (`/api/worker/status` or `/api/config`) and surface:
- `Batch paused: API transport unavailable`
- with explicit instruction to restore dev server and reattach/retry

### Caveat

This does **not** solve the Mand01 stale-state issue by itself; it only improves messaging for the Qasr01-style “next speaker never launched” case.

## Fix 4 — make forced-align thread init idempotent / early-safe

### Objective

Stop `Aligner.load()` from crashing when CPU thread settings are applied after other torch work began.

### Minimum safe change

Guard the interop-thread calls so they only run once and tolerate the “already started” case.

For example:

```py
_TORCH_THREAD_LIMITS_SET = False

if resolved_device == "cpu" and not _TORCH_THREAD_LIMITS_SET:
    try:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # Log once; thread limits are best-effort in a hot server process.
        pass
    _TORCH_THREAD_LIMITS_SET = True
```

A better variant is to separate:
- `set_num_threads(1)`
- `set_num_interop_threads(1)`

and only swallow the specific late-init failure for the latter.

### File targets
- `python/ai/forced_align.py`
- tests under `python/test_*`

### Acceptance criteria
- CPU aligner load no longer crashes in a hot thread-mode process.
- Mand01-type run completes STT+ORTH+IPA (modulo any unrelated alignment/content issues).

## Fix 5 — prefer persistent worker for IPA-heavy live runs

### Objective

Move the live runtime off the fragile `thread` path for repeated aligner usage.

### Evidence basis

Repo comments already describe the persistent worker as the durable architecture for avoiding repeated `Aligner.load()` churn.
The current live process was still:

```bash
python/server.py --compute-mode=thread
```

### File/ops targets
- launcher / deployment docs
- whichever script starts the local PARSE dev runtime

### Acceptance criteria
- live runtime starts with `--compute-mode=persistent` where appropriate
- `/api/worker/status` returns live persistent-worker data
- cold-start cost is paid once, not on first IPA request mid-batch

---

## Proposed implementation order

1. **Backend fix first:** `forced_align.py` interop-thread guard
   - highest certainty root cause
   - immediately removes the IPA blocker

2. **Frontend state-model fix:** preserve `jobId` + distinguish `start` vs `poll` failures
   - prevents false Mand01-style postmortems

3. **Report reconciliation on download**
   - ensures exported JSON is forensically useful

4. **Transport preflight / clearer pause state**
   - improves Qasr01-style UX when the proxy dies again

5. **Runtime hardening:** move launcher toward persistent worker
   - reduces likelihood of this whole class of aligner-init issues

---

## Concrete regression tests to add

### Frontend

`src/hooks/__tests__/useBatchPipelineJob.test.ts`
- `start succeeds, first poll throws network error -> outcome preserves jobId and marks poll-phase disconnect`
- `start fails before job id -> outcome marks start-phase failure`

`src/components/shared/__tests__/BatchReportModal.test.tsx`
- disconnected outcome renders distinct banner text
- download payload includes `jobId` / `errorPhase`

### Backend

Add a test for `forced_align.py` / server IPA aligner load where:
- mocked torch raises on `set_num_interop_threads`
- aligner load path degrades safely instead of crashing the pipeline job

---

## Short-form findings

- **Mand01:** started successfully, later completed backend-side, but the UI lost contact and exported a stale false-negative.
- **Qasr01:** never started because the Vite `/api` proxy path was down.
- **Backend bug:** IPA aligner fails in thread mode due to late `torch.set_num_interop_threads(1)`.
- **Frontend bug:** batch outcome model cannot distinguish “never started” from “started but disconnected”.
- **Reporting bug:** downloaded batch report serializes stale client state without live reconciliation.

---

## Recommended PR split

### PR A — backend
`fix(ipa): guard torch interop thread init during aligner load`

### PR B — frontend
`fix(batch): preserve job ids across poll disconnects and reconcile downloaded reports`

### PR C — runtime/ops/docs
`docs(runtime): prefer persistent worker for local batch compute`

This report PR is the investigation artifact that should be referenced by the implementation PR(s).
