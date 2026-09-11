# NeuroLoop session memory

- GitHub handoff: project documentation is indexed in `docs/README.md`, with the overall overview in root `README.md`. Source publication excludes weights, credentials, environments and `data/` evidence. The flat assistant PNG is available but not wired into the current page. Publishing does not clear the inference hold.

Updated September 10, 2026 after the 21:47 Pacific crash. This file records state, not permission to claim incomplete work is finished.

- Root: `D:/NeuroLoop`. Frontend in `frontend/src`; backend in `backend/neuroloop`. Local website 3010, API/MCP 8010, marimo 2718.
- **GPU inference and Launch are held.** `data/inference-quarantine.json` persists the hold. Do not remove it, replay the crashed run or conduct more inference without diagnosis and an approved revised bounded test. No drivers, firmware, registry or clock settings were changed.
- Latest crash: Windows 0x113, parameters 0x19/0x2/0x10de/0x27e0, dump `C:/Windows/Minidump/091026-18312-01.dmp`; current access denied. See CRASH-RECOVERY.md. 90°C and low RAM were observed, not proven causal.
- Current services start only web/API/marimo. New queued work is rejected in shared services; standalone worker/Launch also check the hold. Existing data remains readable.
- 29 real cortical arrays and 32 asset hashes passed recovery checks. SQLite intact, zero active runs. Fresh isolated silent evaluation `cdfaacce-e365-4eca-8447-ba323c64d5e5`, 6×20484, 42.485 seconds. Latest AV baseline completed89.437 seconds, reference crashed.
- Failed local run `5df6542e-b183-4a08-b05e-adcf81175aed`, ARIA proposal `0e2bcff4-94fe-4759-bf64-972e464bfb41`, W&B `n8jfg4uh`. Local failed and remote crashed status confirmed; baseline retained. Do not call Launch acceptance complete.
- Isolated `.runtimes/app`110, model192, wandb-mcp121 packages; app/model rehearsal directories also pass checks. Old system-inheriting envs preserved. Local TRIBE/MoviePy packaging forks and spaCy3.8 wheel documented. App/npm advisory scans clear; model Accelerate mitigation and setuptools scoped triage remain caveats.
- 109 backend tests passed, including process termination, pressure hold and blocked queue; production frontend built. Recovery audit16 checks pass. Clean second model media test passed, second-install full inference not passed.
- Weave credentialed in private `.env`, actual traces delivered, SQLite outbox/readback/retries. W&B Models metadata published. ARIA real review completed. Restricted v1 Launch job/queue installed, now paused. Official W&B MCP19 readonly tools and NeuroLoop18 configured/SDK-verified. Current thread may need client reload.
- marimo real ledger has seven useful experiment plot tabs, tables and saved cortical timelines. No Molab upload.
- UI: retain white/navy/teal, original NeuroLoop logo and real anatomy. Dedicated `/neuro` page replaces floating dialog. Generated ribbon artwork + SVG companion, real local commands, session draft, actual-request pixel shimmer/elapsed loading, cinematic footer reveal/marquee/magnetic CTA/background paths. No fake microphone, unavailable model dropdown or pretend AI replies.
- User defers W&B Inference/web AI generation, CoreWeave cloud/storage, TypeSafe, Kragel and TSAM validation. Neuro free-text conversation stays unavailable; external agents can use MCP. No public product requested.
- Migrations and restore implemented;539-file backup restored twice, then a fresh560-file post-crash backup restored successfully with the execution hold. Older backups receive a hold on restore. Preserve source weights, media, DB, evidence and execution hold. Some model directories are junctions.
- Read AUDIT.md, REQUEST-RECONCILIATION.md and REMAINING-WORK.md. Earlier audit state archived under `docs/archive/20260910-pre-recovery` is historical.
