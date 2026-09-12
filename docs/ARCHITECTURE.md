# Architecture

Browser → Next.js authenticated proxy → FastAPI CPU application → transactional database + immutable object storage.

One notebook → authenticated outbound job claim → shared registry → W&B reasoner / image model / video model / vision / TSAM / TRIBE / TypeSafe → immutable result upload → idempotent completion.

The initial PLAN allocates a bounded candidate set. Each subsequent PLAN receives real parent creatives, source references, evaluations, feedback, budgets and contextual strategy observations. Regeneration inputs always include the parent output and original selected references. A candidate file is never overwritten.

The application persists each transition before dispatch. One global active model job is the conservative baseline; SQLite write transactions and a PostgreSQL advisory lock enforce serialization. Notebook-local FileLock and model lock prevent accidental concurrent GPU calls. All weights need not be resident simultaneously: configure explicit park/activate hooks.

Cheap deterministic validation precedes vision evaluation. Top candidates can proceed to optional/required TSAM and TRIBE. Required model/configuration mismatches or unknown constraints block selection. TypeSafe chooses among allowed actions and eligible IDs; code rechecks confidence, budget, lineage and human gates. A queue timeout does not become a successful result.

The CPU Meta queue and Weave delivery outbox are separate from notebook work. No application browser request holds a GPU inference request open. Failed or ambiguous remote mutations retain their evidence and stop rather than pretending a retry is safe.

This is currently a single-owner application with separate human, agent and worker roles, not an audited multi-tenant SaaS deployment.
