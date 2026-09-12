# Current state audit â€” 2026-09-12

## Scope and initial state
Writable target: D:\NeuroLoop (initially only .git and LICENSE). Reference-only: D:\NeuroLoopV1. The connected filesystem is Windows, not the MacBook path mentioned in the request; code and launchers will be portable, current writes use the explicit D: target. No changes to V1, no copying secrets or downloaded models, no local GPU inference.

## Inspection
Read V1 AGENTS.md, README.md, installed TypeSafe skill, frontend package manifest/API proxy/BrainCanvas, backend configuration/generation/integrations/telemetry/TSAM/TRIBE profile code, requirements and agentic-loop review. Inventoried backend, frontend, documentation, infrastructure, scripts and research source. Historical V1 test and execution claims are not new-project verification.

## Reusable work
Premium Next.js/React landing/styles/brand assets; Three.js fsaverage5 surface; Brain Lab/evaluation/comparison/chart components; FastAPI/Pydantic patterns; media validation; TRIBE/TSAM provenance and interpretation boundaries; Weave receipts; MCP and marimo source. Preserve relevant source without environments, databases, weights, private results or credentials.

## Incomplete and conflicting work
- generation.py contains deferred H3/Ideogram providers, not working generation.
- integrations.py marks TypeSafe disabled; installing its skill did not activate it.
- V1's deterministic-edit loop is not the requested multimodal regeneration tree.
- V1 local SQLite/process architecture must not be mistaken for durable app plus notebook execution.
- V1 README records a Windows graphics-crash hold and unestablished GPU stability. Do not clear it or run local model jobs.
- No new notebook endpoint/model callables or new-project sponsor credentials are verified.
- No V1 module is declared dead just because it is not selected. Preserved UI components need new API wiring before being advertised as migrated.

## Migration
Retain V1 source and visual assets; introduce a separate active versioned campaign API. Persist immutable assets, candidate parents, inputs, prompts, versions, evidence, decisions, failures and approvals. One notebook registers real image/video/TRIBE/TSAM/vision adapters and serializes model work, with explicit offload/unload hooks. App-owned durable state survives notebook restart. Outbound worker transport is not a provider-rule exemption: require permitted deployment, never expose unsupported molab tunnels. Missing contracts or services remain NOT_CONFIGURED/UNAVAILABLE; no runtime mock fallbacks.

## Initial integration status
TypeSafe: project skill read; live docs unreachable from browsing environment; contract not yet verified.
W&B Inference: official OpenAI-compatible contract verified, no credentialed call made.
Weave: official tracing contract verified; V1 has an outbox to study.
ARIA, Meta, object storage, notebook: not configured/exercised in new target.

## Verification gates
CPU-only schema/state/queue/auth/artifact/cancellation tests, frontend typecheck/build, real local API smoke. Separate acceptance requires actual notebook models, compatible evaluator checkpoints, real sponsor calls, persisted lineage, full trace and human-gated PAUSED Meta path. Never claim complete end-to-end model execution from unit tests.

## Implementation update
The new active package is backend/neuroloop_app; original backend/neuroloop is preserved but not started. Real TypeSafe documentation was retrieved and archived under docs/vendor; its structured decision client is implemented but no credentialed call was made. The new isolated environment, shared notebook worker, durable app, frontend, paused-only Meta client, Weave exporter and restricted MCP are implemented. 36 CPU tests and the frontend build passed on this Windows machine; browser and stdio MCP smoke checks passed. FFmpeg/ffprobe were checksum-verified and installed only inside this target. See VERIFICATION.md and LIMITATIONS.md for the remaining live notebook/model/sponsor/production gates. No V1 source hash changed across the 218 migrated reference files.
