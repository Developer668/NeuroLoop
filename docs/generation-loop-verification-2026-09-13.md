# Real generation verification — 2026-09-13

Campaign `ee3561ad-d534-4918-9eba-c33033a37715` was created through the local web UI. Run `6e0e9622-11e9-4060-8782-de58e9dc2196` completed real W&B GLM planning, TypeSafe plan review, MiniMax H3 FP8 generation, authenticated media upload, and GLM vision evaluation.

The browser loaded and played asset `8fda1b1a-60d1-43e5-9cbb-fc8119226ce8`: 1024×576, 24 fps, five seconds, with audio. SHA-256: `a6752ac7dd496472d74cff8d62a44ac3860720fc0ee94fc4f8db5e944e53444e`. The local verification copy is `artifacts/verification/neuroloop-real-ad.mp4`; the structured receipt is `artifacts/verification/generation-loop-verification.json`.

The hosted notebook was running an older vision adapter. Evaluation initially failed schema validation. The live and saved notebook integration now attaches exact sample timestamps from validated frame indices, preserves provider responses, and removes only an empty, unsupported constraint `description` annotation. Nonempty unexpected fields remain invalid. The web's retry action successfully evaluated the existing asset without regenerating it.

The successful vision response reported creative quality 0.82 (confidence 0.70), a model estimate from six frames, not a measured audience response. It left product identity and audio claims UNKNOWN. The engine correctly stopped at READY_FOR_REVIEW with INSUFFICIENT_EVIDENCE_OR_CONSTRAINT_FAILURE. No final TypeSafe selection, automatic revision, TSAM, or TRIBE execution was verified by this run. Full-loop verification must remain false.

Additional fixes: optional evaluators can be routed to a separate online research worker; retry state reflects the resumed stage; readiness telemetry preserves successful generation and evaluation even when a candidate is subsequently ineligible. H3 adapters expose actual model phases to worker heartbeats. The creation form keeps media controls visible and offers five-, ten-, and fifteen-second video lengths.

Validation: production frontend build passed. Loop, plan-gate, integration, notebook, and telemetry test suites passed; targeted regression tests cover separate-worker routing, offline-worker exclusion, evaluation retry state, empty annotation handling, invalid frame indices, and preservation of ineligible candidates in execution telemetry. Test fixtures are not execution evidence; the campaign and provider receipts above are the real integration evidence.

The local service and authenticated cloud worker connection were restored. The current quick-tunnel URL depends on the running local tunnel; this is not a verified 24/7 deployment.
