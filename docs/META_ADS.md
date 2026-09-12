# Real Meta handoff

The UI Experiments page and `/api/v2/experiments` create an immutable review: candidate asset/hash, account, page, objective, destination, budget/currency, targeting, special categories, text and licensing acknowledgement. Only an eligible evaluated creative may be drafted.

An authenticated human session must type APPROVE PAUSED DEPLOYMENT against the current digest, then DEPLOY PAUSED to enqueue actual creation. Worker/agent keys cannot approve. Creation runs in a separate durable CPU queue; the browser receives 202, not a five-minute request.

Real paths verified against Meta's official generated Python SDK: adimages/advideos, campaigns, adsets, adcreatives, ads and insights. Each mutation writes an intent before HTTP and its returned ID/hash afterward. Campaign/ad-set/ad statuses are explicitly PAUSED and must read back PAUSED before DEPLOYED. Currency mismatch prevents creation. A missing mutation acknowledgement produces NEEDS_RECONCILIATION, not an automatic duplicate. Partial objects are preserved, never silently deleted.

Video uses an actual uploaded video and an ffmpeg-derived thumbnail; asynchronous Meta video processing may require a human retry after processing. The adapter does not invent a video-ready result. Configure a currently supported `NEUROLOOP_META_GRAPH_VERSION` and server-side `META_ACCESS_TOKEN`, permissions and account/page access. No token/version is prefilled or inferred from an old environment.

No activate/budget-increase/billing route exists. The app can ingest real reports after any separately authorized manual delivery. Reports retain dates, raw fields and INCONCLUSIVE status, feed available intervention records, and never announce a winner from a larger early number. Report polling is on-demand, not an autonomous recurring campaign-spend controller. Special-category/regional policy requirements must be reviewed for the actual account; this first adapter is not a universal campaign-objective implementation.
