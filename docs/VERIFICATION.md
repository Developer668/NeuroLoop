# Verification record â€” 2026-09-12

These checks were executed against D:\NeuroLoop on the connected Windows machine, not inferred from NeuroLoopV1's historical results.

## Passed
- Python: 36 tests, 0 failures, 0 errors, 0 skipped; 7.663 seconds. JUnit: data/verification/cpu-tests.xml. Includes bounded regeneration/lineage, immutable receipts, idempotency, cancellation, lost leases, evaluator compatibility, TypeSafe validation, role separation, paused Meta contracts and static migration upgrade/downgrade.
- Frontend: Next.js 16.3.4 production build passed, including TypeScript compilation. The earlier standalone TypeScript check also passed.
- Notebook: marimo check completed with no issues after formatting with the installed marimo 0.24.2 formatter. Opening the notebook does not download or invoke neural models.
- Browser: actual Chromium headless run with GPU/WebGL disabled passed. Root redirects to /workspace; local bootstrap login creates an HttpOnly session; Command Center, Settings, Experiments, Learning, Lineage and Brain Lab navigation works; authenticated campaign/capability reads and logout work. No browser JavaScript errors. No campaign was created or fake creative seeded. Receipt: data/verification/browser-smoke.json; screenshot: data/verification/workspace.png.
- MCP: real stdio initialization, list_tools and get_capabilities against the running application passed with the restricted agent key. Eight tools; no approval/activation tool. Receipt: data/verification/mcp-smoke.json.
- V1 preservation: recomputed hashes of all 218 reference source files in docs/V1_MIGRATION_MANIFEST.json; no differences.
- New .env, frontend/.env.local, virtual environment, runtime data, transfer files and media tools are ignored by Git. No commit or push performed.

## Running local development application
Frontend: http://localhost:3010/workspace
CPU API: http://127.0.0.1:8010
Start/restart command: .\.venv\Scripts\python.exe scripts\start.py

The tested capability response reported zero workers/jobs, local object storage, development SQLite, Weave/Meta NOT_CONFIGURED, ARIA MANUAL_RESEARCH_IMPORT and model execution NOTEBOOK_ONLY. This is an empty real workspace, not a replay of demonstration data.

## Not verified or complete
No live GPU model inference, W&B/TypeSafe credentialed execution, remote Weave trace receipt, actual Meta campaign creation/activation, PostgreSQL/S3 deployment, remote notebook network connection or automatic ARIA call occurred. Sponsor HTTP responses and generative/evaluator outputs in unit tests are test doubles confined to tests/. They are not registered in runtime NeuroLab.

The full acceptance flow in the supplied directive still requires the actual notebook adapters, credentials, approved reachable backend, generated media, compatible evaluation outputs, real sponsor receipts and human-reviewed Meta objects. The current implementation is not a claim of completed live end-to-end acceptance or production security certification. See LIMITATIONS.md.

## CPU media tools
FFmpeg and ffprobe 9.0.1 were installed under .tools/ffmpeg after verifying the full archive against its reviewed vendor SHA256. Both executables passed -version. New-project configuration points to those files; no system PATH changes or neural/GPU execution. Provenance: docs/FFMPEG_RECEIPT.json.
