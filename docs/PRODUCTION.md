# Deployment checklist

Local development is SQLite + immutable local files; it is real durable state, not a production scale claim. Production settings require PostgreSQL, S3-compatible media storage, stable HTTPS API/frontend origins, strong distinct role keys and explicit migrations.

1. Provision an approved CPU API host, PostgreSQL database and object-store bucket. Configure network ACLs, TLS, backups, IAM and secrets.
2. Install the active package and CPU ffmpeg/ffprobe. Build Next.js using its lockfile; set server-only NEUROLOOP_INTERNAL_API. Do not put server credentials into NEXT_PUBLIC variables.
3. Set NEUROLOOP_ENVIRONMENT=production, NEUROLOOP_AUTO_MIGRATE=false, NEUROLOOP_DATABASE_URL=postgresql+psycopg://..., NEUROLOOP_STORAGE=s3 and bucket/endpoint/credential settings. Use URL-encoded passwords where needed.
4. Apply `alembic upgrade head`; run API and Next.js behind the reviewed reverse proxy. Never import the legacy neuroloop.main module as the new server.
5. Configure the notebook's public API URL/worker key and confirm provider workload permission. Keep receipt/cache storage durable.
6. Execute the real acceptance flow in DEMO_FLOW.md. Confirm live Weave readbacks, object-store restart behavior, PostgreSQL concurrency and real model results before calling it production-ready.

Only the CPU unit/API/migration/UI checks actually recorded in VERIFICATION.md have passed. No cloud deployment, PostgreSQL/S3 fault-injection, multi-tenant audit, GPU fit test or supported provider ingress has been claimed. Simple S3 streaming currently lacks full HTTP range forwarding; optimize this before large-scale video serving.
