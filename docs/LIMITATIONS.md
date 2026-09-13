# Explicit limitations

## Unverified external execution
Actual H3/image/vision adapters are wired into the shared molab notebook; TRIBE/T-SAM checkpoints remain missing there and full-loop GPU execution is unverified. No local GPU inference is run because V1 records a crash hold. Same-notebook placement does not establish GPU memory fit. No W&B/TypeSafe/Meta secret was copied from V1 or invented, and live GLM vision/planning, TypeSafe exact-plan review, and Weave readback receipts are recorded in [the architecture audit](AGENT_ARCHITECTURE_AUDIT.md).

## Scientific/commercial interpretation
TSAM and TRIBE are proxies, not direct viewer measurements. Stochastic regeneration changes multiple features, so comparisons are variant-level. Meta reports may be delayed/empty/confounded; statistical experiment winners, attribution calibration and proven commercial improvement are not implemented. Review research/model/media licenses before advertising use.

## Incomplete product breadth
The core bounded agent is implemented, but a fully conversational command-center agent, every legacy V1 chart/page, a polished graph-edge DAG, automatic ARIA invocation, held-out strategy-policy replay/activation/rollback, neural model training and autonomous scheduled Meta experiment management are not implemented. Legacy components are preserved, not all rewired to the new API. NeuroLab exposes real evidence/tables/JSON; it does not fabricate plots when time series are absent.

## Operational scope
Development SQLite/local storage is tested separately from production PostgreSQL/S3, which requires deployment validation. One active model job is conservative and not benchmarked throughput. Blocking GPU calls support cooperative cancellation, not guaranteed instantaneous preemption. Uncertain external writes require human reconciliation. Provider restrictions apply even to outbound notebook polling. No unsupported public molab tunnel is created.

## Security scope
Single-owner role separation is not multi-tenant enterprise authorization. Do not expose local development ports or secrets. Review production TLS/IAM/ACLs/rate limiting, data retention, database backups and object-store range serving before public launch.
