# ARIA outer-loop integration: explicit boundary

Implemented: real run export (including failures, lineage and observations), a research view in NeuroLab, contextual intervention memory, and typed policy-proposal intake with source `ARIA` or `human`, cited real run IDs, source receipt, immutable digest and PROPOSED state.

Workflow: analyze the actual W&B project/traces with the available ARIA interface; retain its real response/reference; submit that sourced proposal through `/api/v2/policies/proposals`. No hard-coded ARIA answer is generated. A source label is user-supplied provenance, not independently authenticated proof that ARIA produced the text.

The public overview at docs.wandb.ai/aria/overview documents ARIA in the W&B project/team interface. A supported direct autonomous ARIA invocation contract was not established for this new integration, so automatic invocation is NOT_IMPLEMENTED. Do not mislabel manual import as an automatic research agent.

Policy proposals cannot activate themselves. Held-out replay, comparative statistical validation, approved activation and rollback are not implemented; the immutable safety/system policy remains unchanged. Strategy observations enter later reasoning context, but no neural fine-tuning or demonstrated generalization is claimed.
