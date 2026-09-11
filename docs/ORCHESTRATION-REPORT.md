# NeuroLoop ten-workstream orchestration ledger

Updated: 2026-09-11 (America/Los_Angeles)

## Protected baseline

- Source checkout: `/Users/adityadas/Desktop/Programming/Hackathons/NeuroLoop`
- Source HEAD: `00c35b7775e22cb274a99d51a65a34b261b1d235` (`main`, one commit ahead of `origin/main`)
- Exact working-state commit: `f5e1132c5513319d41a15a40c461b9b73210f60b`
- Protected ref: `checkpoint/pre-orchestration-20260911`
- Integration branch/worktree: `codex/integration-20260911` at `/Users/adityadas/Desktop/Programming/Hackathons/NeuroLoop-orchestration/integration`
- External recovery archive: `/Users/adityadas/Desktop/Programming/Hackathons/NeuroLoop-checkpoints/2026-09-11T-neuroloop-pre-orchestration`
- Recovery artifacts: full repository bundle, binary tracked patch, staged patch, untracked file list/archive, status, checkpoint commit ID, and SHA-256 digests.
- The original checkout remained dirty and unchanged after checkpoint creation. No model/data asset was moved, deleted, reset, cleaned, or overwritten.

### Baseline verification

- Backend: `117 passed, 1 skipped` with two dependency deprecation warnings.
- Frontend typecheck: passed.
- Frontend production build: passed with Next.js 16.3.4/Turbopack.
- Services: API, web, worker, and marimo processes running; API, web, and marimo HTTP checks returned 200.
- Inference quarantine: active. Reason: available system memory fell below the 1.5 GiB execution reserve. Cause is not confirmed; explicit approval is required before a revised bounded test. No fresh inference was run during baseline verification.
- Key fingerprints:
  - `app-macos.lock`: `a40f8b03ad35dd6420299dfe704512525542657dd2693586d3063951e770dd9e`
  - `model-macos.lock`: `31b8ae4c69cf239113042a4a99a551b1b6916035a1230682008290fec4d5c0e4`
  - TRIBE brain checkpoint: `9c79ffff6b642b7b0c71d558c935fb3fa33f2788bfb509feead94fafbba2f321` (708,856,138 bytes)
  - Quantized video weights: `3681964db6dba65f62eb2889a95e47a78854cc74aef75f27405bf28d1c1464d2` (1,039,943,688 bytes)

## Strict workstreams

Every workstream uses `gpt-5.6-luna` with maximum reasoning in an isolated Codex worktree created from the protected baseline (or from the reviewed integration branch when it has dependencies). Agent reports are untrusted until the integration guardian inspects the diff and reruns relevant acceptance tests. Required report fields: summary, files changed, commands/tests, evidence, known limitations, commit hash, and exactly one verdict: `COMPLETE`, `REVISE`, or `BLOCKED`.

| # | Workstream | Dependencies | Status | Guardian verdict |
|---|---|---|---|---|
| 1 | Protected baseline plus real-model/MPS memory/E2E investigation | baseline | DISPATCHING | pending |
| 2 | Scientific response stack: TRIBE/Kragel/TSAM/ensemble, temporal targets, provenance | baseline | DISPATCHING | pending |
| 3 | CreativeStrategist, typed interventions, A/B/C branching, policy learning | 2 contracts | QUEUED | pending |
| 4 | CreativeConstraints plus media quality/corruption gates | 2 contracts | QUEUED | pending |
| 5 | Complete MCP closed-loop contract and external-agent iteration | 2, 3, 4 | QUEUED | pending |
| 6 | MCP adversarial/security/reliability and REST/MCP parity | 5 | QUEUED | pending |
| 7 | ImprovementBrief/Copilot and grounded Neuro assistant | 2, 3, 5 | QUEUED | pending |
| 8 | Worker recovery, immutable cache/artifacts, execution guard, reproducibility | 2, 3, 4 | QUEUED | pending |
| 9 | Browser E2E, export bundle, marimo, modalities, product completeness | 5, 7, 8 | QUEUED | pending |
| 10 | Sponsor/provider truth, clean-install/performance audit, independent final release audit | all prior | QUEUED | pending |

## Universal acceptance rules

- Mocks may prove control flow only. Real-model and real-provider acceptance are labeled separately and cannot be inferred from compilation or mocked tests.
- Never bypass the execution guard, MPS reserve, Windows crash quarantine, fixed evaluator profiles, budgets, ownership checks, constraints, or keep/revert rules to make a test pass.
- Never invent calibrated human-emotion, conversion, or neuroscience claims from relative model evidence.
- No fake provider request, receipt, credential, cloud delivery, or sponsor capability may be represented as working.
- Preserve last validated assets through every failure; generated artifacts and evaluation provenance must be immutable and hash-linked.
- Shared domain services are authoritative. HTTP, UI, and MCP must not contain duplicate optimization logic.
- Keep changes lean and readable; avoid speculative frameworks, giant abstractions, unbounded autonomy, or RL.
- Final status is `RELEASE` only after the independent workstream 10 audit passes the integrated system. Otherwise the verdict is `NO-RELEASE` with exact blockers.

## Integration review log

No workstream result has been accepted or merged yet.
