# TypeSafe decision kernel

Verified against live official TypeSafe docs on 2026-09-12: docs.typesafe.ai/api.md, primitives/choice.md, confidence.md, sdk/python.md and the function-calling cookbook. Retrieved documentation is saved in docs/vendor. No undocumented API is used.

The client POSTs to `https://api.typesafe.ai/v1/systemone` with bearer credentials, a configured model (`jev-latest` default), explicit state and named choice questions. Questions select action, candidate and strategy from allowlisted options; response options/probabilities/confidence must pass strict validation.

Inputs include actual EvidenceBundles, budgets, constraints, authorized actions/creative IDs and past decisions. The deterministic engine rechecks the response and enforces confidence, evaluator compatibility, lineage, generation limits and approval rules. TypeSafe cannot unlock spending, approve itself, invent assets, rewrite immutable policy or bypass failed checks.

Malformed responses are bounded failures/retries, not successful decisions. No key or live-call result has been assumed. Setting a key configures a client; a verified live receipt is a separate acceptance gate.
