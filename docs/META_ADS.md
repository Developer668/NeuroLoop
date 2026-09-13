# Real Meta handoff

Publish Ads handles the common, real cross-provider action: connect Meta and upload an existing NeuroLoop image/video into the selected Meta ad account's creative library.

NeuroLoop also retains a separate Meta-only deployment subsystem under `/api/v2/experiments` for reviewed PAUSED campaign creation. That path is intentionally not mixed into the lean cross-provider Publish Ads UI because campaign/objective/targeting semantics are Meta-specific.

An eligible evaluated creative may be drafted for Meta deployment with an immutable review containing the exact creative asset/hash, account, page, objective, destination, budget/currency, targeting, special categories, text and licensing acknowledgement. A Meta OAuth authorization created through Publish Ads can supply the server-side access token; the older static `META_ACCESS_TOKEN` remains supported as a fallback.

An authenticated human must type `APPROVE PAUSED DEPLOYMENT` against the current digest, then `DEPLOY PAUSED` to enqueue actual creation. Worker/agent credentials cannot approve. Campaign, ad-set and ad statuses are forced to PAUSED and must read back PAUSED before the deployment is considered complete.

A missing mutation acknowledgement produces `NEEDS_RECONCILIATION`, not an automatic duplicate. No activation, budget-increase or billing route exists. Real reports may be retrieved after separately authorized manual delivery, but NeuroLoop does not turn early metrics into an automatic winner claim.
