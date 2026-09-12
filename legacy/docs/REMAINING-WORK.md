# Remaining work and release gates

Latest: [loop design and verified Weave repair](AGENTIC-LOOP-REVIEW.md), [TSAM metadata and scientific validation audit](SCIENTIFIC-VALIDATION-AUDIT.md). The user has excluded graphics-crash diagnosis from the present work; the existing GPU hold is preserved. CPU-only acceptance tooling does not itself establish Launch acceptance.

General GPU/Launch execution is paused after repeated Windows 0x113 graphics crashes. Fresh bounded CPU-only verification now works without changing that hold; see [fresh execution](FRESH-EXECUTION.md). This table distinguishes completed implementation from unpassed acceptance.

| Work | Current state | Evidence still required |
|---|---|---|
| Isolated pinned environments | Implemented; five clean environments pass dependency checks; clean app tests and model media workflow pass | Full inference from the second model installation after crash diagnosis; final multimodal stability remains unpassed |
| Dependency advisories | App/npm scans clear; model matches triaged; checkpoint guard implemented | Upstream Accelerate fix or stronger review of all loading paths; ongoing advisory review and complete native/vendor scope |
| Windows graphics crash | **Blocking.** Three known 0x113 incidents; current model/Launch hold enforced | Readable dump analysis, driver/hardware diagnosis, approved revised workload and repeat telemetry runs |
| Weave export | Connected, actual delivered receipts, durable retries implemented | Operational monitoring over longer use; delivery guarantees remain bounded by provider availability |
| ARIA/Launch | Real ARIA review, strict v1 contract, installed queue, restricted agent and result adapter | Successful approved bounded experiment through local keep/revert and remote result readback; latest experiment crashed |
| Migrations and restore | Versioned transactional migrations, validated backup/restore and two successful rehearsals | Scheduled retention/rotation and recovery on another physical machine are not yet exercised |
| Capability/documentation drift | Current hold, hardware and agent heartbeat checks; weight presence separated from inference proof | Keep statuses tied to new evidence when runtime/model versions change |
| Quantization accuracy | Historical local quantized-inference evidence exists; runtime-local weights are not included in this checkout | Representative held-out original-versus-quantized comparison, per-modality metrics and acceptance thresholds |
| Commercial permissions | Unresolved | Documented rights for intended use of upstream models, software and datasets; TRIBE/TSAM restrictions remain relevant |
| Kragel registration/scoring | Adapter and seven source volume pairs present; manifest hashes verified. Experimental readiness does not establish registration or transfer validity | The volumes already exist. Establish a provenance-bound surface-to-volume registration, reproduce original reference scoring, then test measured-fMRI to synthetic-TRIBE transfer |
| TSAM integration | Fresh Windows strict loading and audiovisual CPU forward pass succeeded in 4.422 seconds, with eight finite logits | Confirm class mapping, reproduce held-out metrics, review leakage and calibrate on the intended domain; one technical clip is not validation |
| W&B Inference / web AI conversation | **User deferred.** No LLM request enabled | Later provider credentials/access, agreed sharing policy and constrained-planner acceptance; web chat needs its own actual conversational contract |
| CoreWeave compute/storage | Awaiting sponsor credits/access; local device only | Explicit cloud authorization, runtime/storage, budget and live acceptance test |
| TypeSafe | Deferred; no runtime call | Agreed provider contract and implementation |
| Public product | Not requested | Tenant isolation, identity, quotas, HTTPS and adversarial review before public use |

The dedicated Neuro page, assistant artwork/SVG, pixel loading, animated footer and background paths are implemented. The component templates were adapted to the installed React/Motion stack; unsupported model selectors, microphone simulation, random voice bars and unavailable creation actions were not exposed as working controls. See [request reconciliation](REQUEST-RECONCILIATION.md).

Next: obtain dump analysis using [CRASH-RECOVERY.md](CRASH-RECOVERY.md). Do not remove the hold merely to finish an integration test. Then design a lower-pressure bounded run and verify the final model environment and Launch workflow. Scientific and commercial activation require their separate evidence.
