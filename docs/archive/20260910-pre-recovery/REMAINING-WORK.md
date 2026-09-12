# Remaining work and release gates

The core local pipeline runs and produces actual outputs. The following work is
still required; passing integration tests does not close these items.

| Priority | Work | Completion evidence |
|---|---|---|
| P1 | Replace both system-package-inheriting Python environments with isolated, pinned environments | Clean installation on a second directory/machine, passing dependency checks, backend/Edge/MCP tests and real inference |
| P1 | Triage Python advisory matches and upgrade compatible dependency sets | Resolve applicable advisories, preserve lockfiles and rerun media parsing, model loading, MCP and full workflows |
| P1 before stability claims | Investigate Windows 0x113 graphics crash | Readable dump analysis and driver/hardware diagnosis; bounded repeat runs with telemetry, no assertion from one success |
| P1 before commercial use | Resolve upstream model, software and dataset permissions | Documented permission for intended use; TRIBE and TSAM currently have non-commercial restrictions |
| P1 for emotion readout | Establish Kragel registration and scoring, then transfer validation | Registration provenance, transforms, alignment checks, reference scoring and held-out evaluation; see RESOLUTION-HANDOFF.md |
| P1 for emotion claims | Validate TSAM on held-out data and the intended domain | Reproduction, class mapping confirmation, leakage checks, metrics and calibration; technical loading alone is insufficient |
| P2 | Verify real Weave export and Inference planner with credentials | Readable trace URL and one constrained proposal followed through the local acceptance rules |
| P2 | Build ARIA/Launch adapter | Versioned job entrypoint, queue/agent, metadata input/output contract, approved bounded run and imported result |
| P2 | Improve operational traceability | Persist external trace IDs/status/errors; reliable flushing/retry without claiming a failed export succeeded |
| P2 | Add deployment-grade migrations and restore tooling | Versioned migrations, database/media consistency checks and successfully rehearsed backup restore |
| P2 | Fix capability/documentation drift | Replace historical-test file inference with current readiness checks; do not equate files existing with runnable services |
| P2 | Validate quantization accuracy | Compare original vs local quantized pipeline on representative held-out data, not merely shapes or successful forward passes |
| Deferred | CoreWeave compute | Explicit cloud authorization, tested container/runtime, storage, credentials, cost limits and telemetry |
| Deferred | TypeSafe | Agreed decision-provider contract and actual implementation; no current runtime call |
| Only if public product requested | Public deployment and accounts | Tenant isolation, real identity, session revocation, HTTPS, limits/quotas, restricted research access and adversarial review |

No destructive environment replacement, driver changes, paid cloud provisioning,
or scientific activation was performed by the documentation audit. These are
concrete outstanding tasks, not hidden features.

## Suggested order

1. Preserve the current working environment and recorded evidence. Build a clean
   replacement next to it and remove dependency/advisory problems there.
2. Diagnose the graphics crash and establish a bounded, repeatable stability test.
3. Complete Weave/Inference setup; build ARIA only after a versioned local job works.
4. Resolve scientific and licensing requirements before exposing emotion claims.
5. Add public-product infrastructure only when public hosting is actually needed.

The current app can be used for the verified local research workflows while its
limitations remain explicit. It must not be advertised as a validated human emotion
decoder or certified production deployment.
