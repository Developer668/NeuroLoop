# W&B reasoning and Weave

Reasoner: official OpenAI-compatible `https://api.inference.wandb.ai/v1/chat/completions`, bearer API key, optional `OpenAI-Project: entity/project`, exact user-configured supported model. PLAN results are schema validated against allocated candidate slots and evidence IDs. No hard-coded concept is returned if the provider is unavailable.

Tracing: one durable root per campaign run; actual jobs, decisions and meaningful deterministic events create child spans. The outbox uses official Weave call start/read/end service contracts at `https://trace.wandb.ai`. Basic authentication uses username `api` and the server W&B API key. Metadata retains lineage/model/policy/timing/error fields; private raw prompts/media are not sent by default.

A link appears only after readback confirms IDs, trace IDs, parentage and completion status. Local outbox records are not proof of cloud delivery. Delivery retries/backoff are bounded, independent of model execution. Enable with `NEUROLOOP_WEAVE_ENABLED=true`, `WANDB_API_KEY`, `WANDB_PROJECT=entity/project` on the CPU API.

Official references: docs.wandb.ai/inference and docs.wandb.ai/weave/reference/service-api/calls/call-start. Credentialed delivery and live sponsor usage remain explicit acceptance checks.
