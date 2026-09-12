# Three-loop implementation audit

Audited September 11, 2026 against both supplied reviews and the current local source. This is a code and test audit, not a new model experiment. No model, provider, execution hold or runtime policy was changed.

Fresh verification: 40 tests passed across strategy, external-agent continuation, response-loop, failure receipts and Launch contracts. A further 53 passed and 3 were skipped across recovery, media constraints, worker provenance and contracts. Total: **93 passed, 3 skipped**, with dependency deprecation warnings. No fresh model inference, live semantic-agent run, policy benchmark or ARIA acceptance was performed. Fixture-based tests are identified below rather than presented as model-output evidence.

## Verdict

The reviews' central concern is supported by the code. NeuroLoop implements a real bounded creative-optimization workflow and context-specific adaptive operator statistics. It does not yet deliver the complete intended creative-reasoning, transferable experience and strategic repair architecture.

The reviews need one qualification: some evidence-responsive behavior already exists. `CreativeStrategist._rank` uses response-gap direction, headline metadata and prior attempts to order supported interventions. That is a deterministic heuristic, not an agent observing the creative and reasoning about a concept. The distinction matters more than whether the class is named “strategist.”

| Loop | Actual implementation | Missing proof or behavior |
|---|---|---|
| A: improve this creative | Frozen contract, rendered edits, model evaluation, sibling comparisons, keep/revert/tradeoff and export | Semantic observation and diagnosis, richer executable interventions, parameter search, complete evidence-to-hypothesis feedback |
| B: improve future experiment selection | Cost-aware Thompson sampling updates success/failure counts inside a strict context | Compatible cross-creative retrieval, versioned transferable policy experience, held-out advantage over fresh/fixed policies |
| C: repair a failing strategy | Rejection counter, action exhaustion, filter-chain limit, honest stops, constrained external continuation interface | Active diagnosis, typed strategic repair actions, tested repair feedback and an accepted ARIA-driven round trip |

## Important source findings

### 1. The semantic planner is not on the live worker path

`worker.py` imports `planner_proposal`, but does not call it. The function in `integrations.py` describes an optional remote request; an occurrence in `scripts/harden_recovery.py` is historical patch-script content, not runtime execution. The current worker calls the deterministic strategist. W&B Inference remains deferred.

External MCP clients can own reasoning through the typed continuation interface. That is a valid architecture, but a client must actually read evidence and make subsequent decisions. Neither an MCP tool list nor a local command chat demonstrates that complete external-agent behavior. The website currently owns the bounded deterministic workflow, not an invisible semantic agent.

### 2. Evidence affects ranking, but not as broadly as the schema implies

`strategy.py:316` maps an increasing gap to upward saturation/contrast/brightness edits, and a decreasing gap to downward edits. Headline timing is preferred for some narrow windows. These rules are not established causal relationships between those edits and emotion evidence.

`worker.py:474` first selects up to three operators with the bandit, then passes only those operators to the strategist. The strategist cannot choose a more relevant family that was omitted from that subset. On the reference-similarity path, the response target is absent and an optional response ensemble may be absent too; generic fallback hypotheses can therefore dominate.

`strategy.py:366` constructs the hypothesis from a template. Its `confidence` is a fixed heuristic (0.65 or 0.35 with a branch decrement), not an estimated or calibrated probability. A structured hypothesis field does not prove semantic planning.

### 3. Named time windows are not executed as localized filter edits

`worker.py:150` extracts `proposal.operator`; it does not use `targeted_window` to restrict the filter. The FFmpeg filter applies to the full video. Consequently, a hypothesis that says “in normalized window …” is describing a diagnostic target, not necessarily the changed interval. The next implementation must distinguish evidence window from intervention scope, or implement a real bounded temporal filter.

Headline timing changes a composition's `headline_start` by a fixed ±0.75 seconds. There is no general parameter-search loop, shot-order editor, product-reveal operator or independent-layer recovery for a flattened video on this path. Keeping unsupported actions unavailable is correct.

### 4. Learning uses exact context and useful-edit rate, not effect magnitude

`worker.py:395` hashes metric, threshold, allowed operators, profile, reference hashes, target, response report, timeline, media kind, constraints and brief. `policy.py:59` retrieves statistics by that exact context and operator.

Selection samples `Beta(1 + successes, 1 + failures)` and divides by average execution cost. `total_gain` is recorded but not used by that selection formula. This is adaptive useful-edit-rate-per-cost selection, not direct expected-gain optimization. There is no compatible-neighbor experience retrieval for a new creative. A changed reference set or brief can start a new context.

### 5. Strategic repair is an unclosed loop

`worker.py:451` stops after two unsuccessful sibling batches. That is a bounded plateau heuristic, not diagnosis. Its message says “edits,” although the counter is updated per batch/lineage. It does not call ARIA, propose a discriminating experiment, revise a parameter region or distinguish ambiguous evidence from ineffective strategy.

`agent_bridge.py:175` creates a deterministic typed intervention for the externally selected operator and replaces its hypothesis with the supplied text. It provides useful contract enforcement, but the input schema does not express a general repair diagnosis, target element, parameter bounds or a stop/repair action taxonomy. A prior ARIA review and an unaccepted Launch experiment do not establish an active strategic repair loop.

### 6. Recovery preserves evidence; restart does not automatically resume experiments

`worker.py:605` marks interrupted running jobs failed and preserves their completed evidence. It explicitly requires a new run to retry. Other worker code can reuse pending lineage records when entered appropriately, but that must not be described as automatic crash resumption. Proposal claims and result persistence have useful idempotency protections; arbitrary interruption at every transition still needs systematic fault-injection acceptance.

### 7. Regional evidence exists, but planner consumption is incomplete

`anatomy.py` supplies parcel summaries and the UI displays 148 anatomical parcels. `readout.py` preserves timestamps and hemisphere means; reference comparison uses eight normalized time bins and reports separate reference scores. Thus the system is more than hemisphere means alone.

However, the strategist does not consume a complete anatomical/temporal candidate-versus-reference difference packet to diagnose a creative problem. Normalized duration alignment is also not event matching. Displaying a regional chart does not prove the planner used it.

## Checklist coverage

Statuses assess the full requirement in the supplied checklist. “Partial” means a real subset is connected; it is not a synonym for complete. Test codes refer to files under `backend/tests`: S=`test_strategy.py`, A=`test_agent_closed_loop.py`, R=`test_response_loop.py`, H=`test_recovery.py`, Q=`test_constraints_quality.py`, P=`test_worker_provenance.py`, C=`test_contracts.py`, L=`test_launch.py`, W=`test_failure_receipts.py`. These are engineering tests, often using fixtures. “None” means no acceptance evidence identified for that full behavior.

| ID | Status | Connected source / evidence | Test or missing acceptance |
|---|---|---|---|
| A1 | Partial | `services.create_run`: brief and numerical objective remain separate fields | C; no semantic goal-resolution proof |
| A2 | Partial | `schemas.RunCreate`: supported objective/readout validation | R; no full unsupported-goal negotiation |
| A3 | Implemented for current action scope | `services.create_run`: frozen request/project/asset metadata | A, P, C |
| A4 | Partial | Worker deterministic; external ownership possible through MCP | A; live semantic owner unverified |
| A5 | Partial | Worker selects ordinary bounded edits automatically | S; richer autonomous experiment missing |
| A6 | Partial | Previous best retained, missing evidence errors and stop reasons | S, R; completion is not improvement |
| B1 | Implemented | Inference artifacts, manifests and provenance | P, H; prior actual outputs in FRESH-EXECUTION.md |
| B2 | Partial | `anatomy.summarize_regions` and atlas metadata | Anatomical output exists; broader mapping validation separate |
| B3 | Partial | Raw timestamps, normalized comparison and displayed timelines | Temporal diagnostic packet not fully consumed |
| B4 | Implemented | `readout.compare_references`, worker worst-reference safeguard | S, C |
| B5 | Implemented for current reports | `response.py`, `tsam.py`, `kragel.py` retain source meanings | R; scientific eligibility remains separate |
| B6 | Partial | `project_context`, `get_evidence`, typed gap/provenance | A; complete planning packet missing |
| B7 | Implemented | Missing/nonfinite evidence fails closed | R, S |
| C1 | Partial | Metadata reaches rules; external client can retrieve assets/evidence | No live multimodal semantic planner |
| C2 | Partial | Typed response gap and templated hypothesis | S; not semantic causal diagnosis |
| C3 | Partial | Expected direction field | S; no comprehensive falsification contract |
| C4 | Partial | Typed operator, parent, branch and exact fixed change | S, A; bounds/element targeting incomplete |
| C5 | Partial | Prior attempts/current accepted response influence rules | S; no closed semantic replanning proof |
| C6 | Partial | Experimental qualifications in reports | Heuristic edit-to-emotion relation unvalidated |
| C7 | Missing as semantic acceptance | Templates and fixed confidence remain | None |
| D1 | Partial | Existing editable composition/headline metadata | Q; no general scene/layer graph |
| D2 | Partial | Six filters and two headline nudges | S; broader interventions absent |
| D3 | Implemented for current operators | Worker rejects headline edits without composition | S, C |
| D4 | Missing | Exact fixed operator values only | None |
| D5 | Partial | Controlled operator chain | Window wording exceeds actual filter scope |
| D6 | Implemented | Worker batch creation and common-parent evaluation | S sibling tests |
| D7 | Deliberately out of scope for generation | Deterministic renders; generation_calls=0 | R; no fake generator |
| E1 | Implemented | Frozen objective, min_gain and reference rules | C, S |
| E2 | Partial | `media_quality` + constraints check media and metadata | Q; metadata is not arbitrary visual-content recognition |
| E3 | Implemented for supported comparisons | Profile/cache contracts and fixed metric | P, C |
| E4 | Partial | Numerical tests and profile checks | No representative no-op/re-encoding sensitivity study |
| E5 | Partial | Tradeoff candidates/records retained | No explicit Pareto-front controller |
| E6 | Implemented | Incumbent survives rejected/failed siblings | S, H |
| E7 | Implemented for current decisions | Saved metric/decision/result lineage | A, P |
| F1 | Partial | Experiment specs and policy outcomes stored | S, A; richer semantic experience absent |
| F2 | Missing for transferable retrieval | Strict context hash is sole statistics lookup | None |
| F3 | Missing | No compatible-neighbor experience retriever | None |
| F4 | Partial | Strict context prevents incompatible pooling | S; no transfer gate because no transfer |
| F5 | Implemented within context | Beta sampling with pseudocounts | S; does not guarantee practical broad exploration |
| F6 | Partial | Invalid outcomes excluded from efficacy statistics, retained as errors | S; no separate learned reliability policy |
| F7 | Partial | Backend/metric identifiers and context statistics | No policy snapshots, rollback or observation-level attribution |
| G1 | Partial | Rejection count, filter cap, invalid evaluator checks | S, H; full failure taxonomy missing |
| G2 | Missing | Errors/stops without active strategic diagnosis | None |
| G3 | Partial | Constrained external intervention proposal | A; general repair actions missing |
| G4 | Partial | Approved intervention executes through worker | A fixtures; real ARIA round trip unaccepted |
| G5 | Implemented for existing continuation | Digest, allowed operator and workflow budgets | A, L |
| G6 | Partial | Mixed-profile changes rejected | C; explicit authorized evaluator transition absent |
| G7 | Partial | Continuation iteration/time/evaluation ceilings | A; external analysis time not fully accounted |
| H1 | Partial | Durable incumbent/evidence, interrupted jobs failed | H; automatic resume not claimed |
| H2 | Partial | Transactional proposal claim and saved lineage reuse | A, S; full interruption matrix untested |
| H3 | Implemented | Atomic manifests and validation | H, P |
| H4 | Implemented for owned execution | Process supervision, timeout and cancellation | H |
| H5 | Implemented with provider limits | Durable delivery and remote readback | W; prior verified remote receipt |
| H6 | Implemented | Execution guard and bounded CPU path | H; hold unchanged in this audit |
| I1 | Implemented for current actions | MCP shares domain services | A schema/interface tests; prior real MCP evidence |
| I2 | Partial | External continuation test exists | A explicitly mocks evaluator/renderer; not live semantic acceptance |
| I3 | Partial | Website and MCP share worker | Same deterministic loop, not complete semantic architecture |
| I4 | Partial | Hypotheses, outcomes, errors and delivery logged | No full meta-action/semantic observation trace |
| I5 | Partial | Prior experiments and policy stats read by worker | No compatible cross-task retrieval or ARIA feedback closure |
| I6 | Partial | Research uses ledger and actual saved responses | No policy-version/meta-repair data to display yet |
| I7 | Partial | Several configuration/execution states distinguished | Full runtime acceptance must remain separate |
| J1 | Implemented | Result references selected managed artifact/export | Prior real outputs; A/P provenance |
| J2 | Implemented | Original, parent, kept candidate and evaluation IDs | A, S, P |
| J3 | Implemented | Failed/invalid/tradeoff/reverted branches retained | S, H |
| J4 | Partial | Bounded local time and evaluation usage | No comprehensive external reasoning/repair cost ledger |
| J5 | Partial | Budget/target/action exhaustion and plateau stops | Ambiguity/tradeoff diagnoses incomplete |
| J6 | Implemented as limited heuristic | Fixed plateau rule, no implemented value-of-information estimate | Must describe it as heuristic |

## What to build next

1. Correct the intervention contract: distinguish diagnostic interval from actual edit scope; expose applicability, exact parameters and required rendered checks. Remove any implication that fixed confidence values are measured certainty.
2. Build a compact evidence packet: source/composition, brief and numerical objective, per-reference temporal differences, eligible readout coverage, prior hypotheses/outcomes, remaining actions and budget. Preserve raw artifact references.
3. Connect one actual semantic owner. External MCP reasoning is viable while W&B Inference remains deferred. Website behavior must identify its actual deterministic mode. Require observation, explanation, expected observable result and a typed intervention in every semantic proposal.
4. Add a small meaningful operator family supported by real editable assets. Parameterize it with declared bounds and controlled coarse-to-fine search. Do not advertise product-layer control for flattened video.
5. Separate exact execution identity from compatible learning context. Retrieve versioned observations under evaluator/objective/constraint compatibility gates, keep cold-start behavior and exploration, and record exactly which observations affected a decision.
6. Add typed strategic recovery states: ineffective intervention, rendering failure, insufficient coverage, objective tradeoff, suspicious gain and action exhaustion. A repair must choose a permitted alternative or stop, spend remaining budget and return through normal acceptance.
7. Close one actual trace-linked ARIA continuation and then run held-out/ablation comparisons. Show the effect of semantic planning, experience retrieval and repair separately.

The two documents are design guidance, not permission to enable deferred providers, add discarded judges or remove execution safeguards. This audit does not implement the proposed new architecture. It identifies what is connected and what needs a deliberate implementation next.
