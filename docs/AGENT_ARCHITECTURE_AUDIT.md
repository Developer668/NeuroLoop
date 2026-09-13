# Agent architecture audit — 2026-09-12

Scope: the supplied NeuroLoop harness architecture, active `backend/neuroloop_app`,
and the H3/Ideogram molab notebook `nb_hmqbzUN6NR96sCQ55RKPXb`.

## Findings and changes

| Requirement | Audit finding and implementation |
| --- | --- |
| W&B GLM vision agent | The live authenticated model catalog lists `zai-org/GLM-5.3-Flash`. Both local planner and vision settings select it. Vision sends actual encoded media; planning now receives original references and current parent media as well as campaign state. |
| Temporal visual evidence | Video extraction sends six midpoint frames with asset identity, content hash, frame index and timestamp. Evaluator frame claims are rejected when they cite unsampled times. This is sparse-frame inspection, not continuous video/audio understanding. |
| Typed observation → evidence → hypothesis → change | Child plans require an `OptimizationHypothesis` inside `EditIntent`, with parent evaluation IDs, an exact recorded response score, visual evidence, hypothesis/confidence, target/instruction and expected metric/direction. Aggregate scores cannot be labeled as temporal response drops. |
| TypeSafe in the execution harness | Planning queues a durable `REVIEW_PLAN` job. The real TypeSafe `/v1/systemone` API reviews the exact plan and evidence. The server validates the choice distribution and plan hash before creating any generation job. Rejection or low confidence stops execution for review. Existing TypeSafe candidate selection remains. |
| State, lineage, comparison | Existing durable campaign snapshots, parent references, evaluation provenance and intervention history are retained. The harness now retains the incumbent when a proposed selection has lower comparable visual-quality evidence. This is a proxy comparison, not proof of commercial lift. |
| Weave around the loop | Review is a separately budgeted, traced job. Trace output now includes edit hypotheses, parent IDs, review hash/choice, selected IDs, response delta and vision provider receipt. The exporter uses real write/readback and records pending delivery honestly. |
| marimo / GPU tools | Existing H3, Ideogram and research adapters are preserved. The user selected the molab notebook, not a new self-hosted machine. The notebook's public preview describes `/jobs` endpoints as a suggested design, explicitly not an existing FastAPI deployment. Live notebook integration is coordinated with the other active task. |
| TRIBE/T-SAM | Actual preserved adapters exist; successful inference through the new full loop has not yet been established. Missing sensors stay unavailable. Neither model establishes CTR, purchasing behavior or measured individual emotions. |

## Live evidence and limits

The authenticated W&B model-list request succeeded. A real call on
`frontend/public/brand/neuroloop.png` returned GLM visual evidence, token usage and
request ID `chatcmpl-bcf44351-37b5-405c-aba9-e71117e5cc1f`.
The receipt is saved in `data/verification/glm-5.3/vision.json`.
A real TypeSafe plan-gate request rejected an empty plan with confidence 0.98,
returning model `jev-1.13.0`.

The corrected real HTTP run passed GLM media inspection, GLM planning, exact-plan
TypeSafe approval, durable result acknowledgement, and Weave trace readback.
Receipt: `data/verification/live-harness-47ee82d3-7153-4341-a011-3eaa7676ae23/receipt.json`.
It records `control_plane_verified: true`, `weave_verified: true`, and
`full_loop_verified: false`. Its queued generation was explicitly cancelled;
no generated output was fabricated.
[Live run trace](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/42e0634c-8206-4427-b2ca-1da73f1ef576).

Combined backend checks: 51 passing tests. The subsequent vision accounting
change passed all eight notebook model tests. `marimo check` and frontend
TypeScript checking also passed. Molab coordination confirmed both generators
registered and provider settings saved privately; TRIBE/T-SAM checkpoints and
the external app connection remained unavailable at that check.

Live verification exposed two defects: an output allowance that truncated a
vision answer, and a generation-parameter JSON schema broader than server
validation. The response allowance is now bounded/configurable and the schema
describes exactly the permitted parameters. JSON mode is enabled; local typed
validation remains mandatory.

`scripts/verify_live_harness.py --media PATH` starts an isolated real HTTP API,
uploads real source media, calls GLM vision/planning and TypeSafe, and checks
Weave readback. It saves receipts under `data/verification/live-harness-*`.
It does not simulate generation or claim full-loop completion.
`--full-loop` additionally requires actual registered model execution and a
completed decision path; its receipt has an explicit `full_loop_verified` flag.

CPU tests use clearly marked fixtures only in `tests/`. Passing those tests is
not evidence of live GPU execution. The full generation → vision → TRIBE/T-SAM
→ revision loop remains unverified until the live notebook is connected and
returns its actual results. No local 12 GB GPU generation is attempted.

Provider references: [GLM model ID](https://wandb.ai/site/inference-model/zai-org_glm-5.3-flash/),
[JSON mode](https://docs.wandb.ai/inference/response-settings/json-mode),
[GLM always-on reasoning](https://docs.wandb.ai/inference/response-settings/reasoning).
