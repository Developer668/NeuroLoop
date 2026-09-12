# Durable data and migration

`migrations/versions/20260912_01_initial.py` declares the initial schema explicitly. Core tables: campaigns, campaign_runs, creative_assets, creatives, generation_jobs, evaluations, decisions, human_feedback, events, workers, auth_sessions, weave_traces, intervention_ledger, strategy_policies and meta_experiments. Exact identifiers, foreign keys and indexes are in the migration and SQLAlchemy metadata.

Campaign/run snapshots freeze product facts, selected references and limits. Asset rows store SHA-256, MIME, decoded dimensions, size and object key; bytes live in local development storage or S3, not database blobs. Creative parent/output IDs preserve all branches. Job rows store state, attempt, lease hash, result hash, progress and failures. Completion requires the matching worker/lease and cannot rewrite a prior result.

`alembic upgrade head` creates a fresh database. For a development database already created by metadata.create_all, compare its schema before an operator deliberately stamps the matching initial revision. Never blindly stamp an unrelated or V1 database. Downgrades are destructive and must not be run against real history without an authorized backup/recovery plan.
