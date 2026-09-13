# Vercel deployment

Public web: https://neuroloop-kappa.vercel.app

The Next.js frontend runs on Vercel. Its server-side `NEUROLOOP_INTERNAL_API` environment variable points to the existing HTTPS tunnel into the laptop's FastAPI service on port 8010. Marimo workers continue polling that backend. The laptop, tunnel, and required workers must remain running. A quick-tunnel restart can change its URL; update the Vercel environment variable and redeploy if it changes.

Remote users must select **Connect with an access token** and use an authorized workspace token. **Connect to this computer** only supports localhost. The operator token grants workspace control and should only be shared with trusted operators. Provider keys remain on the existing compute runtimes.

Deploy from `frontend` using `vercel deploy --prod --scope jerry-wens-projects`. The Vercel project is `neuroloop`. GitHub automatic deployment was not connected: Vercel rejected the repository connection. CLI deployment succeeded.

The Vercel build disables standalone output to avoid the Next.js 16.3 adapter packaging failure. Local standalone builds retain their existing configuration. `.vercelignore` excludes local environment files and generated builds.

Verified on September 13, 2026:

- Production cloud build and TypeScript completed.
- Edge opened the public homepage and workspace sign-in.
- An authenticated client signed in through the Vercel route and retrieved capabilities, campaigns, the real MeowStore video run, and evidence (HTTP 200).
- H3 video and Ideogram image byte ranges returned HTTP 206 with correct media types.
- TRIBE evaluation `514970a9-c013-4d76-969f-1aa1a66c4d09` frame 1 returned actual cortical data (HTTP 200).
- The verification session was revoked afterwards.

This verifies deployment connectivity and existing evidence retrieval. It does not establish a new generation run, completed automatic revision, unlimited upload sizes, or uninterrupted 24/7 availability.
