# Sponsor integrations: implemented, connected and planned

Status reflects the local audit, not the presence of a sponsor name in the UI.

| Tool | Actual state | Implementation |
|---|---|---|
| marimo | Running and browser-verified | `research/lab.py` reads the actual SQLite ledger and saved evidence; port 2718 |
| Weights & Biases Weave | Implemented, not credentialed or remotely verified | `telemetry.py` wraps run/evaluation spans; `integrations.record_evidence` emits experiment metadata |
| W&B Inference | Implemented, not credentialed or remotely verified | `integrations.planner_proposal` calls an OpenAI-compatible endpoint; worker considers a validated proposal |
| CoreWeave ARIA | Planned integration, not operational | Status/help links only; no working Launch job submission/result adapter found |
| CoreWeave compute | Deferred | Local RTX GPU is used; no cloud resources provisioned or tested deployment container found |
| TypeSafe | Disabled/deferred | No active service, model or implemented decision provider |

## Weave

Open [W&B authorization](https://wandb.ai/authorize) in your own signed-in browser.
Choose an entity/project you can write to. Enter the key privately in the root
`.env`; never paste it into this document or chat:

```dotenv
WANDB_API_KEY=<your private key>
WANDB_PROJECT=<entity>/<project>
NEUROLOOP_WEAVE_ENABLED=true
```

The implemented path uses `weave.init`, run/evaluation calls and experiment metadata.
It intentionally sends selected identifiers, timings, decisions and numerical
metrics, not raw media or cortical arrays. Failures preserve local results.
There is not yet a durable per-run external trace receipt or guaranteed export
retry/flush mechanism; a key is not proof of delivery.

Restart the owned services. Run **Check service connections**, then a bounded real
experiment. Confirm the corresponding trace exists in the actual W&B project and
matches local run/evaluation IDs. Save its URL as the acceptance receipt.
[Official Weave quickstart](https://docs.wandb.ai/weave/quickstart).

## W&B Inference

The same key must have appropriate Inference access and billing/credits. This is
an optional remote LLM request; local TRIBE execution does not depend on it.

```dotenv
NEUROLOOP_PLANNER_ENABLED=true
NEUROLOOP_PLANNER_URL=https://api.inference.wandb.ai/v1
NEUROLOOP_PLANNER_MODEL=openai/gpt-oss-20b
```

The model above is the current code default; verify account/model availability
before enabling it. The request includes the project brief (up to 2,500 characters),
allowed operators and compact baseline evidence. Thus enabling the planner sends
the brief externally, unlike local-only operation. The response must select a
permitted operator and a textual hypothesis. It cannot alter the budget, objective
or acceptance rules. No paid planner call was made in this audit.

Acceptance: perform one small authorized planner request, record the provider/model
and accepted schema, then verify the proposed edit follows the normal local model
evaluation and keep/revert logic. A connection check does not run this request.
[Official Inference documentation](https://docs.wandb.ai/inference).

## ARIA and Launch

ARIA can investigate W&B experiment context and use Launch for approved experiments.
For NeuroLoop, the intended bridge is a versioned job that reads an explicit
experiment specification, submits permitted work to the single local queue, and
publishes bounded results. **That bridge has not been built.** Adding a key or
opening an ARIA link will not create it.

Required inputs: W&B entity/project, ARIA access, Launch queue, permitted compute
target, running agent, source/runtime version and agreed metadata sharing policy.
Build the job entrypoint and result adapter, ensure it cannot bypass the GPU lock,
and verify one approved job end to end. Keep model weights frozen and the local
acceptance contract intact. Cloud compute remains deferred.

[ARIA overview](https://docs.wandb.ai/aria/overview) and
[Launch job/queue/agent walkthrough](https://docs.wandb.ai/platform/launch/walkthrough).

## marimo, CoreWeave and TypeSafe

marimo is already launched by `Start-NeuroLoop.cmd`; open http://localhost:2718.
It reads actual recorded timelines and experiment data. It is local and read-only
in its intended app workflow, not a public research portal.

CoreWeave requires a separate tested compute deployment; no account setup is
needed for the present laptop workflow. TypeSafe is intentionally not called.
Neither should be represented as an integrated sponsor merely because it appears
in capability/help text.

See [CONNECTIONS.md](CONNECTIONS.md) for MCP, which is a separate local agent interface.
