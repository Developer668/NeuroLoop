# Security model

Separate root operator, human session, agent and worker credentials. Human sessions are hashed in the database, expire and can be revoked. Next.js keeps the session in an HttpOnly SameSite cookie; sponsor/object-store/worker secrets remain server-side. Agent tokens cannot exchange themselves for human sessions. Worker tokens authorize jobs/assets only.

Local sign-in requires a separate server bootstrap secret and loopback request. Production rejects weak/missing secrets, local storage/SQLite and non-HTTPS public origins. Production must not enable local bootstrap.

Write-origin checks, per-identity process-local rate limits, total request/upload caps, decoder/MIME validation, safe object keys, signed media URLs, cross-campaign reference checks, output ownership, typed decisions and auditable financial gates are implemented. A supplied filename is not used as a filesystem path. Remote outputs cannot upload arbitrary host files. No arbitrary LLM-generated code or React is executed.

Deployment limitations: this is a single-owner security model, not tenant-isolated enterprise SaaS. Distributed rate limiting, OIDC/team membership, malware scanning, centralized secret rotation, database/object-store backups and cloud IAM hardening require deployment work. Local file chmod on Windows is not a substitute for reviewed Windows ACLs. Do not expose the development server publicly.
