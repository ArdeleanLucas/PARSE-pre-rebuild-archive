# MCP / Agent Integration Roadmap

Historical roadmap for making PARSE a first-class citizen in agent-driven workflows. Most core milestones below are now shipped on `main`; the remaining section is the real future-work list.

---

## 1. Expose all 50 ParseChatTools via MCP

**Status:** ✅ Complete

**Shipped:**
- `python/adapters/mcp_adapter.py` exposes a curated **32-tool default task surface** by default.
- Task 3 adds 3 workflow macros on top of that base, so the current default adapter surface is **36 tools total** including `mcp_get_exposure_mode`.
- Opt-in config at `config/mcp_config.json` (or fallback root `mcp_config.json`) enables the full **50-tool** `ParseChatTools` surface; with the 3 workflow macros and `mcp_get_exposure_mode`, the current full adapter surface is **54 tools total**:

```json
{ "expose_all_tools": true }
```

**Notes:**
- Default behavior remains curated for external agents rather than mirroring the entire in-app chat surface.
- The internal chat dock still uses `ParseChatTools` directly; this task only changes MCP exposure.
- Newly exposed tools now also include the generic job observability trio (`jobs_list`, `job_status`, `job_logs`) alongside the earlier write/export/pipeline helpers.
- `mcp_get_exposure_mode` lets external agents self-inspect whether the active MCP server is running in the default or full-exposure mode.

---

## 2. Richer, safer tool definitions

**Status:** ✅ Complete

**Shipped:**
- MCP-visible PARSE tools now publish strict JSON Schemas from `ChatToolSpec.parameters`.
- Tool metadata includes PARSE-specific safety payloads in `meta["x-parse"]`, including:
  - `mutability`
  - `supports_dry_run`
  - `dry_run_parameter`
  - `preconditions`
  - `postconditions`
- Mutating and job-starting tools now expose dry-run previews where supported.
- Long-running starters are classified as `stateful_job`, so agents can distinguish read-only inspection from direct mutation and from queued/background work.

This means agents can now inspect machine-readable tool contracts instead of inferring risk and workflow semantics from prose alone.

---

## 3. High-level composite / workflow tools

**Status:** ✅ Complete

**Shipped:**
- Added `python/ai/workflow_tools.py` with a dedicated `WorkflowTools` class.
- New macros are exposed via MCP with their own `ChatToolSpec` metadata:
  - `run_full_annotation_pipeline(speaker_id, concept_list, dryRun=False)`
  - `prepare_compare_mode(concept_range, speakers, dryRun=False)`
  - `export_complete_lingpy_dataset(with_contact_lexemes=True, dryRun=False)`
- The macros orchestrate existing low-level tool handlers directly rather than duplicating business logic:
  - annotation workflow: `stt_start` → `stt_status` → `forced_align_start` → `forced_align_status` → `ipa_transcribe_acoustic_start` → `ipa_transcribe_acoustic_status`
  - compare prep: `speakers_list`, `annotation_read`, `cognate_compute_preview`, `cross_speaker_match_preview`
  - export bundle: `contact_lexeme_lookup`, `export_lingpy_tsv`, `export_nexus`
- Each macro publishes machine-readable preconditions/postconditions and supports `dryRun` where appropriate.
- MCP adapter now exposes the workflow macros in both default and full-exposure modes.

Macros are easier to discover, easier to prompt, and safer to execute.

---

## 4. Observability & control layer

**Status:** ✅ Complete

**Shipped:**
- Generic HTTP observability endpoints:
  - `GET /api/jobs`
  - `GET /api/jobs/{jobId}`
  - `GET /api/jobs/{jobId}/logs`
- Matching MCP tools:
  - `jobs_list`
  - `job_status`
  - `job_logs`
- Shared job payloads now include structured progress, `errorCode`, `logCount`, and lock metadata.
- Heavy job starters can carry a `callbackUrl`, so external automation can receive the final generic job payload on `complete` / `error`.
- Speaker-scoped lock metadata prevents humans and agents from mutating the same resources silently in parallel.

These changes make long-running PARSE jobs inspectable across the UI, HTTP automation, and MCP clients with one consistent status shape.

---

## 5. Standardize the external API surface

**Status:** ✅ Complete

**Shipped:**
- `python/server.py` now serves a full **OpenAPI 3.1** document at `GET /openapi.json` plus interactive docs at `GET /docs` and `GET /redoc`.
- Added a read/write **HTTP MCP bridge** on the same server:
  - `GET /api/mcp/exposure`
  - `GET /api/mcp/tools`
  - `GET /api/mcp/tools/{toolName}`
  - `POST /api/mcp/tools/{toolName}`
- Added shared schema/discovery helpers under `python/external_api/` so the HTTP MCP bridge and stdio adapter reuse the same MCP metadata source of truth.
- Added the official publishable **`parse-mcp`** package scaffold under `python/packages/parse_mcp/` with:
  - `ParseMcpClient`
  - LangChain wrappers
  - LlamaIndex wrappers
  - CrewAI wrappers
- Added `docs/mcp-schema.md` and expanded `README.md` / `docs/api-reference.md` to document:
  - the MCP schema
  - exposure modes
  - the local authentication model
  - the OpenAPI endpoints
- The standardized external HTTP surface now also includes non-MCP agent-relevant helper routes such as:
  - `GET/POST /api/clef/config`
  - `GET /api/clef/catalog`
  - `GET /api/clef/providers`
  - `GET /api/clef/sources-report`
  - `POST /api/clef/form-selections`

These routes matter because current PARSE agent workflows are not limited to the MCP tool catalog; external clients may also need first-class access to CLEF setup, provenance inspection, and reference-form selection state over HTTP.

**Notes:**
- Existing HTTP and MCP tool behavior remains unchanged; Task 5 standardizes discoverability, schemas, and packaging around the current surface.
- The local PARSE HTTP API remains workstation-local and is **not bearer-protected**. Provider credentials continue to be managed separately via `/api/auth/*` and local `config/auth_tokens.json`.

---

## 6. Streaming responses (WebSocket)

**Status:** ✅ Complete

**Shipped:**
- Added an additive WebSocket sidecar in `python/external_api/streaming.py` rather than migrating the custom HTTP server to a new framework.
- The sidecar runs on `PARSE_WS_PORT` with default port `8767`.
- Per-job subscription endpoint:
  - `ws://<host>:<ws_port>/ws/jobs/{jobId}`
- Current v1 event types:
  - `job.snapshot`
  - `job.progress`
  - `job.log`
  - `stt.segment`
  - `job.complete`
  - `job.error`
- First supported realtime workflow is STT:
  - live job progress updates
  - provisional partial segment packets while decoding
- Generic job events (`job.snapshot`, `job.progress`, `job.log`, `job.complete`, `job.error`) are reusable across job types; `stt.segment` is the STT-specific additive packet.
- Existing HTTP polling and callback flows remain fully supported and are still the compatibility baseline.

---

## 7. Future / nice-to-have

| Idea | Value |
|------|-------|
| Built-in sandbox / permission system | Scope an agent to a single speaker: `"agent can only edit speaker X"` |
| Remote / cloud mode | Run PARSE headless on a GPU server; agents connect via MCP over the internet |
