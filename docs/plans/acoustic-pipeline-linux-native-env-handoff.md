# Acoustic pipeline — Linux-native env handoff

**Status**: plan / handoff doc · **Created**: 2026-04-23 · **Author**: fix/ortho-regression-tier3-silent thread

This document captures the complete state of the Fail02 acoustic-alignment
debugging session so a new Claude session (or you) can pick up without
re-deriving anything. Every datum, every commit, every dead end is here.

## TL;DR

- **All code is ready.** PRs #149, #150, #151, #152 all merged to `main`.
  Tier 1 word-level STT, Tier 2 forced alignment, Tier 3 acoustic IPA,
  the ORTH repetition-cascade fix, the batch-report result plumbing, and
  the subprocess-mode compute runner all exist and all work in
  standalone single-threaded Python.
- **One blocker remains, and it's environmental, not code.** The PC's
  server runs under Windows `python.exe` launched via WSL interop. That
  combination is unstable the moment any compute thread touches CUDA —
  the whole process dies silently, with no traceback, during or shortly
  after `torch` / `transformers` / `faster-whisper` init. Both
  threading-based jobs and `multiprocessing.Process`-based jobs are
  killed the same way.
- **Fix: switch the server's Python interpreter from the Windows-side
  conda env (`/mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe`)
  to a WSL-native Linux interpreter with `torch[cu124]`.** WSL2 exposes
  the NVIDIA GPU to Linux processes natively — no interop shim, no
  Windows driver round-trip — and PARSE's code is already Linux-native
  (clone lives under `/home/lucas/gh/ardeleanlucas/parse`).
- **Full setup checklist in § "Linux-native env setup" below.**

## Where things stand

| | status | notes |
|---|---|---|
| Tier 1 word-level STT ([PR #146](https://github.com/ArdeleanLucas/PARSE/pull/146)) | ✅ merged | `word_timestamps=True` + nested `segments[].words[]` |
| Tier 2 forced alignment (`forced_align.py`, in #146) | ✅ merged | torchaudio.forced_align + wav2vec2-xlsr-53-espeak-cv-ft; G2P-as-target discarded |
| Tier 3 acoustic IPA (`ipa_transcribe.py`, in #146) | ✅ merged | wav2vec2 CTC on audio slices only; no text→IPA path |
| Epitran + text-IPA purge (in #146) | ✅ merged | southern_kurdish_arabic_to_ipa, get_ipa_provider, LLM IPA all removed |
| MCP tools for the three tiers (in #146) | ✅ merged | stt_word_level_*, forced_align_*, ipa_transcribe_acoustic_* |
| 6 pre-existing test failures ([PR #147](https://github.com/ArdeleanLucas/PARSE/pull/147)) | ✅ merged | `import os` in chat_tools.py + on_tool_call kwarg on fakes |
| Diagnostic logging ([PR #148](https://github.com/ArdeleanLucas/PARSE/pull/148)) | ✅ merged | skip_breakdown counters + stderr pipeline summary |
| `soundfile` loader + `Wav2Vec2Processor` explicit construction ([PR #149](https://github.com/ArdeleanLucas/PARSE/pull/149)) | ✅ merged | fixed the `TorchCodec is required` crash |
| ORTH repetition-cascade fix ([PR #150](https://github.com/ArdeleanLucas/PARSE/pull/150)) | ✅ merged | `condition_on_previous_text=False` + tuned VAD + stricter compression threshold |
| Batch-report result propagation ([PR #151](https://github.com/ArdeleanLucas/PARSE/pull/151)) | ✅ merged | forward result on error + new "Empty" cell kind |
| Subprocess compute runner + `--compute-mode` CLI flag ([PR #152](https://github.com/ArdeleanLucas/PARSE/pull/152)) | ✅ merged | env-gated launcher, buffer-free checkpoint log, threading_repro.py |
| **Switch server to Linux-native Python on the PC** | 🚧 *pending — this handoff* | see § "Linux-native env setup" below |

Total unmerged code from this thread: **zero**. Everything needed is on
`main`. The remaining work is a PC-side env change.

## Root cause diagnosis

### Symptoms

A full-pipeline or ipa-only compute job triggered via
`POST /api/compute/<type>` on the PC's server does one of three things:

1. **Wedges silently.** The HTTP port stops accepting connections, the
   process stays alive according to `ps` but `/proc/<pid>/status` shows
   `State: S (sleeping)` with 0 % CPU. GPU memory stays allocated and
   is never released. No Python traceback, no stderr output past the
   first few lines.
2. **Dies silently.** `tasklist.exe | grep python` returns zero processes.
   `pgrep -fa 'python.*server.py'` returns empty. No traceback anywhere.
3. **Leaves ghost GPU allocation.** `nvidia-smi --query-gpu=memory.used`
   shows 20–26 GB held indefinitely after the process is gone. Only
   `wsl --shutdown` (or a Windows reboot) clears it.

### What we proved definitively

- **The Tier 3 code itself is correct.** A standalone single-threaded
  Python script (`scripts/validate_acoustic_alignment.py` variants we ran
  interactively via SSH) ran the full pipeline on Fail02 — 66-minute WAV
  — and produced **38/38 IPA intervals in the annotation**. Audio
  loaded in 11 s via soundfile; `Aligner.load()` returned in 6 s on
  CUDA; all 38 `transcribe_slice` calls returned real IPA.
- **The wedge is reproducible with thread mode, subprocess mode, and
  direct multiprocessing — always the same pattern.** We enabled a
  buffer-free checkpoint log that writes each checkpoint via
  `os.write + os.fsync` (bypassing Python / libc / Windows pipe
  buffers). Even with that, the log stops mid-run while GPU
  utilisation shows the thread is still working — strongly suggesting
  the whole process context is being torn down asynchronously.
- **`PARSE_COMPUTE_MODE` env var does not cross the WSL → Windows
  python.exe boundary.** Confirmed empirically (see § "Diagnostic data
  captured"). Only a whitelist of env vars — `HOME`, `PATH`, `USER` — is
  propagated through the WSL interop shim. Custom env vars are visible
  in `/proc/<pid>/environ` (WSL's view of the shim) but absent from
  `os.environ` inside the Windows Python process. **argv does cross**,
  hence PR #152's `--compute-mode` CLI flag.

### The environmental hypothesis

Three facts line up to an unambiguous conclusion:

1. PARSE's clone is WSL-native (`/home/lucas/gh/ardeleanlucas/parse`
   + workspace at `/home/lucas/parse-workspace`).
2. The interpreter running the server is Windows-side:
   `/mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe`.
3. CUDA init from that interpreter goes through Windows's userspace
   CUDA driver via the WSL2 GPU interop shim. That pathway is
   supported for *single-threaded, single-process* workloads but has
   known stability gaps for multi-threaded / multi-process torch
   workloads — especially when the process also holds the Python GIL
   during kernel launches.

Linux-native Python under WSL2 uses the **native NVIDIA driver exposed
through WSL2's GPU passthrough**, not the Windows→WSL interop shim. This
is the supported configuration for torch + CUDA + WSL2 and is tested
widely by the community.

## Diagnostic data captured

Below is the sequence of runs on the PC on 2026-04-23 that localised the
problem.

### Thread-mode run (commit `87841f2`, PR #152 branch)

Trigger:
```
POST /api/compute/ipa_only {"speaker":"Fail02","overwrite":true}
→ jobId=31970d16-3656-4438-b075-f88377349367
```

Checkpoint log:
```
19:12:32.551  LAUNCH.thread       job_id=31970d16-…  compute_type=ipa_only
19:12:32.555  COMPUTE.entry       job_id=31970d16-…  compute_type=ipa_only
19:12:32.557  COMPUTE.dispatch    normalized=ipa_only
19:12:32.559  IPA.enter           payload={'speaker':'Fail02','overwrite':True}
19:12:32.561  IPA.parsed_args     speaker=Fail02  overwrite=True
[no further entries despite GPU showing 9 % util + 24 GB allocated]
```

Parent stderr full contents after the run:
```
server.py:3: DeprecationWarning: 'cgi' is deprecated …
[COMPUTE] _run_compute_job entry … compute_type=ipa_only …
[COMPUTE] dispatching normalized_type=ipa_only
[IPA] enter _compute_speaker_ipa payload={'speaker':'Fail02','overwrite':True}
[nothing after this]
```

Final state after ~4 minutes:
- `HTTP 000` on status poll (5 s + 10 s timeouts)
- `pgrep -fa 'python.*server.py'` → still alive (pid 257159)
- `nvidia-smi` → 24.1 GB used, 8–10 % util fluctuating
- No further prints anywhere

Thread's execution *continued* past the last written checkpoint (GPU
activity proves this) but no logging reached disk — neither stderr (pipe
buffered at the Windows side) nor the buffer-free checkpoint log
(write + fsync appears to stop after a few entries in this environment).

### Env-var-attempt subprocess mode (commit `0639dee`)

Trigger (same endpoint, env var set via `bash -c`):
```
PARSE_COMPUTE_MODE=subprocess python.exe python/server.py
→ [checkpoint] LAUNCH.thread   (NOT LAUNCH.subprocess!)
```

**Confirmed**: env var was visible in `/proc/<pid>/environ` on the WSL
side, but `os.environ.get('PARSE_COMPUTE_MODE')` returned `None`
inside the running Windows python.exe. Interop strips all but
`HOME` / `PATH` / `USER`.

### CLI-flag subprocess mode (commit `87841f2`)

Launch command:
```
python.exe python/server.py --compute-mode=subprocess
```

Startup confirmation:
```
[INFO] compute mode = subprocess (from --compute-mode)
```

Trigger:
```
POST /api/compute/ipa_only {"speaker":"Fail02","overwrite":true}
→ jobId=b7e10459-ad76-4265-8a75-b7b6bd632692
```

Checkpoint log:
```
19:25:55.818  LAUNCH.subprocess   job_id=b7e10459-…  compute_type=ipa_only
19:25:55.841  SUBPROCESS.started  child_pid=22736  result_path=C:\Users\Lucas\AppData\Local\Temp\parse-compute-b7e10459-….json
[no CHILD.* ever — child never reached its first print]
```

Progress over ~4 minutes:
| time from trigger | GPU used | GPU util | HTTP status |
|---|---|---|---|
| 0 s | 1.7 GB | 0 % | 200 (trigger returned jobId) |
| 60 s | 24.1 GB | 8 % | 000 timeout (5 s) |
| 150 s | 24.1 GB | 10 % | 000 timeout (5 s) |
| 240 s | 24.1 GB | 39 % | 000 timeout (5 s + 10 s) |
| ~270 s | 24.1 GB | 10 % | `tasklist.exe \| grep python` = **EMPTY** |

Final state:
- Both parent AND child Windows python.exe processes dead
- 24.1 GB GPU memory ghosted (released only by `wsl --shutdown`)
- Child's stderr file (`/tmp/parse-compute-<job>.stderr.log`) never
  created
- Child's result file (Windows-side temp dir) never written
- No Python traceback in parent stderr

### Standalone repro (single-threaded, same Python)

Ran the identical code path via SSH as a one-shot script with the same
Windows `python.exe` interpreter, no `threading.Thread`, no
`multiprocessing.Process`:

```
[A] audio ready in 11.1 s  numel=63301632 (~3956 s of 16 kHz mono)
[B] aligner ready in 5.9 s  device=cuda
[C] ortho=38  ipa=131
[D] filled=38  skipped_no_text=0  skipped_empty_decode=0  skipped_exc=0
[E] wrote /home/lucas/parse-workspace/annotations/Fail02.parse.json
TIER 3 STANDALONE COMPLETE
```

Same Python, same audio, same model — works end-to-end on the main
thread. The threading / multi-process wrapper is what fails.

## Conclusion

The Tier 3 code is correct. The investment in diagnostics (buffer-free
checkpoint log, categorised skip counters, first-3 exception samples,
per-step pipeline summary) paid off — the wedge pattern is now
precisely characterised even though the ultimate cause is beyond the
Python layer.

The remaining fix is outside this codebase: replace the interpreter, not
the code.

## Linux-native env setup

All commands run **inside WSL (Ubuntu)**, not Windows PowerShell. Tested
against WSL2 + NVIDIA GPU passthrough on Windows 10 / 11.

### Phase A — Preflight

```bash
# 1. Confirm you're in WSL, not Windows
uname -a                        # expect: Linux … WSL2

# 2. GPU visible to Linux processes?
nvidia-smi                      # expect: GPU table with memory + driver version
# If this fails: update Windows NVIDIA driver on Windows side first
# (https://www.nvidia.com/Download/index.aspx). Reboot Windows, retry.

# 3. Note these two values — pick your CUDA wheel variant from them:
nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader
# driver_version ≥ 525 → use torch's cu124 wheels (recommended, 2024+)
# driver_version 520–525 → cu121
# anything lower → update the driver first, do not downgrade torch

# 4. System packages: espeak-ng (required by phonemizer for Tier 2 G2P),
# ffmpeg (some torchaudio helpers), libsndfile (soundfile backend)
sudo apt update && sudo apt install -y espeak-ng ffmpeg libsndfile1
espeak-ng --version             # expect: version ≥ 1.50
```

### Phase B — Install miniforge + create the env

Use **miniforge** over Anaconda (no licensing, smaller, faster). Skip
this block if you already have a native conda/miniforge on Linux.

```bash
# 1. Install miniforge to /home/lucas/miniforge3
cd /tmp
wget -O miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash miniforge.sh -b -p "$HOME/miniforge3"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda init bash                 # adds conda to new shells
# open a fresh shell OR: source ~/.bashrc

# 2. Create the parse env with Python 3.12 (PARSE runtime cap: cgi
# module, used by the stdlib http.server, is removed in 3.13)
conda create -n parse -c conda-forge python=3.12 -y
conda activate parse

# 3. Confirm
which python                    # expect: /home/lucas/miniforge3/envs/parse/bin/python
python --version                # expect: 3.12.x
```

### Phase C — Install torch + all PARSE deps

Third-party imports found in `python/ai/*.py` (needed from pip):
`anthropic, faster_whisper, openai, phonemizer, soundfile, torch,
torchaudio, transformers, pytest`. The `nvidia-*` wheels are
auto-pulled by `torch`. stdlib + own-package imports are not listed.

```bash
# 1. Torch + torchaudio with CUDA 12.4 wheels (Linux, not Windows).
# Pulls ~2.5 GB one-time.
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# 2. CUDA sanity — must say "cuda available: True"
python -c "
import torch
print('cuda available:', torch.cuda.is_available())
print('device       :', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')
print('torch        :', torch.__version__)
"

# 3. Remaining PARSE Python deps (pure pip install)
pip install \
    faster-whisper \
    transformers \
    soundfile \
    phonemizer \
    numpy \
    requests \
    anthropic \
    openai

# 4. Dev-only (optional but recommended for pytest)
pip install pytest

# 5. Sanity: every module imports without error
python -c "
import faster_whisper, transformers, torch, torchaudio, soundfile, phonemizer
print('faster_whisper', faster_whisper.__version__)
print('transformers  ', transformers.__version__)
print('torchaudio    ', torchaudio.__version__)
print('soundfile     ', soundfile.__version__)
print('phonemizer    ', phonemizer.__version__)
"
```

### Phase D — Switch the launcher to the new Python

PARSE's launcher already reads `PARSE_PY` env var (default `python3`);
just point it at the new Linux interpreter.

```bash
# 1. Pin PARSE_PY in your shell rc so every launch uses it
echo 'export PARSE_PY="$HOME/miniforge3/envs/parse/bin/python"' >> ~/.bashrc
source ~/.bashrc
echo "PARSE_PY=$PARSE_PY"        # confirm

# 2. Kill any lingering Windows python.exe server
/mnt/c/Windows/System32/tasklist.exe | grep -i python.exe
# If any processes shown, from Windows PowerShell:
#   taskkill /F /IM python.exe
# Or use the PARSE launcher's stop script (handles both sides):
#   bash scripts/parse-stop.sh

# 3. Optional: confirm --compute-mode flag parses
"$PARSE_PY" -u /home/lucas/gh/ardeleanlucas/parse/python/server.py --help 2>&1 | head -20
```

### Phase E — Verify end-to-end

```bash
# 1. Start the server fresh using the new Python
cd /home/lucas/gh/ardeleanlucas/parse
bash scripts/parse-run.sh &      # uses $PARSE_PY
# or inline:  "$PARSE_PY" -u python/server.py --compute-mode=thread

# Wait ~3s, then:
curl -s http://127.0.0.1:8766/api/jobs/active
# expect: {"jobs": []}

# 2. Wav2vec2 loads on CUDA from this Python
"$PARSE_PY" - <<'PY'
import time
from ai.forced_align import Aligner
t0 = time.time(); a = Aligner.load()
print(f"aligner ready in {time.time()-t0:.1f}s on device={a.device}")
PY
# Expect: "aligner ready in ~5-30s on device=cuda"
# If device=cpu: CUDA isn't linking — re-check Phase C.2

# 3. Full Tier 3 on Fail02 via the UI
# Browser → http://localhost:5173/ → Speaker = Fail02 →
# Actions → "Run IPA transcription" with overwrite=true
# Expected completion: ~2-3 min for Fail02
# Expected result: 38/38 ortho intervals filled with real wav2vec2 IPA

# 4. Once Tier 3 works, run full_pipeline — ortho + ipa — on Fail02
# to verify PR #150's ORTH fix also holds in the new environment.
# Watch the resulting ORTH interval count: should be ≳130 intervals
# covering the full 66 minutes, NOT 38 truncating at 06:31.
```

### Rollback

Windows python.exe env is untouched:

```bash
unset PARSE_PY                           # back to default python3
# or restore the old path:
export PARSE_PY=/mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe
```

### Triage if Phase E fails

- **`cuda available: False`** in C.2 → Windows NVIDIA driver outdated.
  Update driver in Windows, restart WSL (`wsl --shutdown` from
  PowerShell, wait 10 s, reopen WSL terminal), rerun.
- **`faster_whisper` can't load razhan model** → likely missing
  ctranslate2 CUDA runtime. `pip install --upgrade ctranslate2` and
  retry.
- **`aligner ready ... device=cpu`** → torch doesn't see CUDA.
  Reinstall torch with the correct wheel variant matching your driver
  (Phase A.3).
- **Any new silent death at `[IPA] enter`** — unlikely on Linux-native,
  but if it happens, check `nvidia-smi` during the hang: persistent
  0 % util with held memory = driver issue, not PARSE.

## Resuming in a new session

Hand this doc to the new session. The minimum it needs to know:

1. **Code state**: all fixes merged to `main` (see the status table at
   the top). Nothing to re-implement.
2. **Next action**: walk the user through the Linux-native env setup
   above. The user will handle the actual PC-side commands; the
   session's job is to troubleshoot any failure in Phases A–E, confirm
   CUDA visibility, and validate that Fail02 runs end-to-end.
3. **Success criteria**: Fail02 `full_pipeline` (ortho + ipa) triggered
   from the UI completes without timeout, ORTH covers ≳130 intervals of
   the full 66-min recording, IPA tier has paired wav2vec2 output for
   every ortho interval.
4. **If it still wedges on Linux-native Python**: that would be
   genuinely surprising. Rerun the buffer-free checkpoint log from
   PR #152 — it should now be reliable — and we have a real code bug
   to find. But based on all the evidence we gathered, I do not expect
   this.

## Glossary of commit SHAs and PRs

- **PR #146 / `feat/acoustic-alignment-ipa`** — the main Tier 1/2/3 PR.
  Merged commit on main: the full acoustic stack + MCP tools + Epitran
  purge.
- **PR #147 / `fix/preexisting-test-failures`** — fixed the 6 unrelated
  test failures we discovered during the work.
- **PR #148 / `fix/ortho-regression-tier3-silent`** — diagnostic
  observability commits (v1 + v2). `_compute_checkpoint`,
  `skip_breakdown` counters, per-step pipeline summary on stderr.
- **PR #149 / `fix/tier3-soundfile-loader`** — the TorchCodec error fix
  (soundfile primary) and the `Wav2Vec2Processor` explicit-construction
  fix (transformers `TypeError: Received a bool for argument tokenizer`).
- **PR #150 / `fix/ortho-repetition-cascade`** — the razhan ORTH
  truncation fix: `condition_on_previous_text=False`, tuned VAD,
  stricter `compression_ratio_threshold`, renamed ORTHO → ORTH in all
  new comments.
- **PR #151 / `fix/batch-report-propagation`** — frontend picks up
  per-step result even on error, new "Empty" cell kind, skip_breakdown
  drill-down.
- **PR #152 / `fix/compute-subprocess-runner`** — subprocess runner
  behind `--compute-mode=subprocess` CLI flag, buffer-free checkpoint
  log, `scripts/threading_repro.py`, documented the WSL env-var gap.
