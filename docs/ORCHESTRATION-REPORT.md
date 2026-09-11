# NeuroLoop ten-workstream orchestration ledger

Updated: 2026-09-11 (America/Los_Angeles)

Current orchestration state: **ACTIVE — DEPENDENCY-GATED INTEGRATION**. The two launcher-created tasks were reconciled as workstreams 1 and 2; no duplicate workstream was created. Later workstreams are provisioned only after their prerequisite integration gates pass.

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
| 1 | Protected baseline plus real-model/MPS memory/E2E investigation | baseline | BLOCKED | accepted investigation; real-model release gate blocked |
| 2 | Scientific response stack: TRIBE/Kragel/TSAM/ensemble, temporal targets, provenance | baseline | COMPLETE | accepted with revision at `11c0b6a` |
| 3 | CreativeStrategist, typed interventions, A/B/C branching, policy learning | 2 contracts | COMPLETE | accepted at `35d6eec` |
| 4 | CreativeConstraints plus media quality/corruption gates | 2 contracts | COMPLETE | accepted at `986f2a0`; integration seam `707e1e3` |
| 5 | Complete MCP closed-loop contract and external-agent iteration | 2, 3, 4 | COMPLETE | accepted with focused revision at `7db9e7f` |
| 6 | MCP adversarial/security/reliability and REST/MCP parity | 5 | QUEUED | pending |
| 7 | ImprovementBrief/Copilot and grounded Neuro assistant | 2, 3, 5 | QUEUED | pending |
| 8 | Worker recovery, immutable cache/artifacts, execution guard, reproducibility | 2, 3, 4 | COMPLETE | accepted at `c29185b` |
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

- Baseline rerun on the integration worktree with the pinned app runtime: `117 passed, 1 skipped`. A clean ad-hoc runtime also exposed missing `data/tmp` bootstrapping and FFmpeg discovery assumptions; those are assigned to workstream 8.
- Luna W1 task `01a08fef-23f5-7121-9f4c-2bb547fa31a5` returned `BLOCKED` at `75d560dd27494d97e5bc69d5808bd12b25a2284d`. Guardian reviewed the complete diff, ran profiler compile/self-test, verified it imports no model code and signals no processes, and integrated it as `a78c670`. The active MPS quarantine recorded 299,040,768 bytes available versus the 1.5 GiB reserve; no fresh full response loop exists.
- W1 was later resumed after the user cleared memory and returned `BLOCKED` again at `c94cbc8808bd5f985cbaf2afdc3345221aaadb75`. The branch adds modality routing and V-JEPA hidden-state compaction, but it predates the reviewed integration branch and supplies no numerical-equivalence test or guarded real inference evidence for the evaluator-changing compaction. It is preserved as evidence for W9/W10 and was not integrated.
- Luna W2 task `01a08fef-23f5-7121-9f4c-2bd112c9d3b5` returned `COMPLETE` at `45ac45e2563cc694b58d8ad50805bc2819702361`. Guardian inspection found overlapping windows could double-count support and partial target coverage could still yield a misleading score. The focused revision `961259815d38630e666e9709d6fb474c77aa1b1d` adds interval-union and per-dimension coverage plus fail-closed partial support; integrated as `11c0b6a`. Combined suite: `144 passed, 1 skipped`.
- Luna W3 task `01a09003-ace0-7311-bacd-aee0b765a847` returned `COMPLETE` at `58121e5d53ff588d7401761427d344352dd077d0`. Guardian inspected the strategy, policy, worker, and tests, reran focused and full tests, and integrated it as `35d6eec`.
- Luna W4 task `01a09003-ace0-7311-bacd-aefbd7ae944b` was interrupted by the account Luna quota after producing a clean worktree. Guardian preserved and inspected all files, reran its nine focused tests plus the full suite, committed the accepted scope as `363160b3d6135adb5dbb1993f044a89385dcdda5`, and integrated it as `986f2a0`. A formal report retry is pending on the same task, not a duplicate workstream.
- Guardian integration commit `707e1e3` wires W4's real decoded-media/declared-constraint report ahead of W3's model evaluation, removes placeholder constraint evidence, and adds a regression proving a rejected candidate never reaches the evaluator. Combined suite at that gate: `141 passed, 1 skipped`; after the W2 revision: `144 passed, 1 skipped`.
- Luna W5 setup `client-new-thread:35715b1d-02ec-41a9-a104-17ad2b01c124` is provisioned from reviewed integration commit `11c0b6a` for the MCP closed loop.
- Luna W8 setup `client-new-thread:89cc7a86-d0f1-4a78-a451-7e6858e043e0` is provisioned from reviewed integration commit `707e1e3` for recovery/cache/guard/reproducibility and the clean-checkout/cache-identity findings.
- Luna W8 task `01a09209-db27-74b2-baed-06ac7afbc4c5` returned `COMPLETE` at `d05fe81635c9250596970791ca38d40429856f0e`. Guardian inspected the streamed stat-cached model/runtime profile, immutable hash-linked evaluation bundle, cache revalidation, process-group recovery, execution guard, clean checkout bootstrapping, and bundled FFmpeg discovery. Focused acceptance: `29 passed, 1 skipped`; integrated as `c29185b`. Two editable vendored packages cannot satisfy strict hash mode, so that clean-install limitation remains explicit.
- Luna W5 task `01a0920a-b717-7f62-8558-6b154b4b0b85` first returned `COMPLETE` at `2616717a411032e37ae8a71a5d0e54781335d23a`. Guardian rejected two acceptance gaps: execution regenerated a proposal instead of consuming the exact reviewed intervention, and open-proposal creation was raceable. The separate revision `1e50635148350927133727cadcd6ca64f297a974` persists and digest-validates the exact typed intervention across first execution and recovery, and serializes the root proposal claim. Guardian reran the 11 focused tests and integrated the pair as `8da4208` and `7db9e7f` while retaining W8's artifact and execution-guard changes.
- Guardian closed the W3/W4 service seam by routing the complete `CreativeConstraints` schema through the authoritative run service instead of rejecting valid copy/logo/object/dimension/audio fields before the worker gate. Focused integration acceptance: `71 passed`; combined backend acceptance after W5/W8 and this seam: `166 passed, 1 skipped`.
- The original checkout remains dirty and untouched. Protected and completed worktrees remain preserved; no model/data/cache/database/quarantine asset was removed or overwritten.
