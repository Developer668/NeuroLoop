# Remaining work and release gates

Current execution is paused after repeated Windows 0x113 graphics crashes. Review and preserve evidence before further model work. This table distinguishes completed implementation from unpassed acceptance.

| Work | Current state | Evidence still required |
|---|---|---|
| Isolated pinned environments | Implemented; five clean environments pass dependency checks; clean app tests and model media workflow pass | Full inference from the second model installation after crash diagnosis; final multimodal stability remains unpassed |
| Dependency advisories | App/npm scans clear; model matches triaged; checkpoint guard implemented | Upstream Accelerate fix or stronger review of all loading paths; ongoing advisory review and complete native/vendor scope |
| Windows graphics crash | **Blocking.** Three known 0x113 incidents; current model/Launch hold enforced | Readable dump analysis, driver/hardware diagnosis, approved revised workload and repeat telemetry runs |
| Weave export | Connected, actual delivered receipts, durable retries implemented | Operational monitoring over longer use; delivery guarantees remain bounded by provider availability |
| ARIA/Launch | Real ARIA review, strict v1 contract, installed queue, restricted agent and result adapter | Successful approved bounded experiment through local keep/revert and remote result readback; latest experiment crashed |
| Migrations and restore | Versioned transactional migrations, validated backup/restore and two successful rehearsals | Scheduled retention/rotation and recovery on another physical machine are not yet exercised |
| Capability/documentation drift | Current hold, hardware and agent heartbeat checks; weight presence separated from inference proof | Keep statuses tied to new evidence when runtime/model versions change |
| Quantization accuracy | Actual local quantized inference exists | Representative held-out original-versus-quantized comparison, per-modality metrics and acceptance thresholds |
| Commercial permissions | Unresolved | Documented rights for intended use of upstream models, software and datasets; TRIBE/TSAM restrictions remain relevant |
| Kragel registration/scoring | **Implemented experimentally.** Published MNI volumes are sampled through fsaverage5 white/pial geometry; pattern expression is persisted and shown separately | Independent measured-fMRI to synthetic-TRIBE transfer validation remains open |
| TSAM integration | **Implemented experimentally.** Strict eight-class CPU checkpoint path and five-second audiovisual windows; can contribute to the explicit response ensemble | Scientific/domain validation and calibration remain open |
| W&B Inference / web AI conversation | **User deferred.** No LLM request enabled | Later provider credentials/access, agreed sharing policy and constrained-planner acceptance; web chat needs its own actual conversational contract |
| CoreWeave compute/storage | Awaiting sponsor credits/access; local device only | Explicit cloud authorization, runtime/storage, budget and live acceptance test |
| TypeSafe | Deferred; no runtime call | Agreed provider contract and implementation |
| Public product | Not requested | Tenant isolation, identity, quotas, HTTPS and adversarial review before public use |

The dedicated Neuro page, assistant artwork/SVG, pixel loading, animated footer and background paths are implemented. The component templates were adapted to the installed React/Motion stack; unsupported model selectors, microphone simulation, random voice bars and unavailable creation actions were not exposed as working controls. See [request reconciliation](REQUEST-RECONCILIATION.md).

Next: obtain dump analysis using [CRASH-RECOVERY.md](CRASH-RECOVERY.md). Do not remove the hold merely to finish an integration test. Then design a lower-pressure bounded run and verify the final model environment and Launch workflow. Scientific and commercial activation require their separate evidence.
