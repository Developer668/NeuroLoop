# System audit — September 10, 2026

**Verdict: the local system produces actual model outputs and passes its functional
checks, but it is not ready for an unqualified production release.** The audit
found dependency consistency and known-advisory problems, incomplete external
integrations and unresolved scientific requirements.

## Fresh checks and output evidence

| Check | Result |
|---|---|
| Backend regression suite | 70 passed, one existing multipart deprecation warning, 4.70 s |
| Next.js production build | Passed; `9sVsz-tVFTO2Ftet0kPQS` |
| Temporary Edge interactions | All eight check groups passed; no reported JavaScript errors |
| Responsive layouts | 390/768 px landing, Brain Lab, Compare, Research and Connections passed |
| HTTP and stdio MCP | Both authenticated/initialized successfully and discovered the same 15 tools |
| New inference through MCP | One actual evaluation; 6 × 20,484 finite cortical values, 44.36 s |
| Fresh peak PyTorch allocation | 2,986,604,032 bytes, approximately 2.78 GiB; not total driver memory |
| All saved arrays | 27 checked, including archived history; summaries recomputed and first API frame matched exactly |
| All managed assets | 31 checked against their recorded SHA-256; all matched |
| Comparison | Recomputed directly from saved NumPy arrays: 0.5695114160613077, matching MCP |
| Export | Fresh ZIP integrity passed; contains actual prediction.npy and selected creative |
| Access checks | Unauthenticated API/MCP denied; foreign-origin session request denied |
| Database/queue | Integrity OK; zero active jobs at runtime audit completion |
| Service lifecycle | Owned services stopped for build, restarted; API/web/research return HTTP 200 |
| Frontend advisory scan | npm audit reports zero known vulnerabilities |
| Python dependency consistency | FAIL: 37 app-environment and 36 model-environment conflict lines |
| Python advisory scan | 83 raw matches, 44 distinct package/advisory IDs across nine packages |

New run: `f10894f3-6412-4bee-a8e6-b109be88d28c`. New evaluation: `637922a4-b133-412a-9b81-ab028b042382`.
[Open the actual result](http://localhost:3010/workspace?view=brain&evaluation=637922a4-b133-412a-9b81-ab028b042382).
The input is a newly rendered six-second silent composition from the retained NASA
lunar photograph, explicitly named as an audit composition. It is not a recorded
human-response experiment. It used one new neural evaluation; model feature caches
can still be reused. Earlier raw NASA video/audio tests are preserved separately.

Fresh MCP calls covered capabilities, status, workspace/evaluation listing,
rendering, project creation, evaluation/progress, evidence, comparison, export and
research retrieval. All 15 tools, including controlled experiments and cancellation,
were exercised in the earlier real-media suite. Those three tool operations were
not presented as new executions in this audit. The configured Codex command was
checked with `codex mcp get neuroloop`; SDK transport tests use that exact command.
The current conversation still does not dynamically acquire newly configured tools.

## Findings

### P1: environments are not isolated or reproducible

Both `pyvenv.cfg` files set `include-system-site-packages = true`. Consequently
unrelated global packages affect resolution. TRIBE declares NumPy 2.2.6,
PyTorch >=2.5.1,<2.7 and torchvision >=0.20,<0.22; the visible installations are
NumPy 2.4.6, PyTorch 2.11.0+cu128 and torchvision 0.26.0. Successful tests establish
that the exercised paths run, not general compatibility with these unsupported
upstream version ranges. The broad backend requirements are not a reproducible lock.

Create isolated replacement environments and pin compatible versions before
switching launchers. Do not blindly downgrade the working shared installation:
other installed applications also have conflicting requirements. Full raw conflict
lists are retained in `app-pip-check.txt` and `model-pip-check.txt`.

### P1: Python advisory matches require triage and compatible upgrades

The advisory lookup covered 122 installed app-environment runtime dependency
versions and their default transitive requirements. It excluded optional extras,
vendored model code, native binaries and packages unique to the other environment.
The service returned duplicate entries; 83 is the raw count, not 83 independent
verified exploits. There are 44 distinct package/advisory IDs; aliases can overlap.

| Package | Installed version | Distinct advisory IDs |
|---|---|---|
| cryptography | 46.0.7 | 4 |
| idna | 3.11 | 1 |
| pillow | 11.3.0 | 18 |
| pydantic-settings | 2.13.1 | 1 |
| pygments | 2.19.2 | 1 |
| pyjwt | 2.12.1 | 5 |
| setuptools | 65.5.0 | 4 |
| starlette | 0.38.6 | 7 |
| urllib3 | 2.6.2 | 3 |

Examples include Starlette multipart resource-consumption issues and Pillow image
parser issues. These packages participate in media handling, so the matches deserve
priority. The upload limit is enforced after multipart parsing; it is not evidence
that parser-level memory risks are closed. Authentication and loopback restrict
exposure but do not repair dependencies. Other advisory prerequisites may be absent
here, such as a particular secret-directory option. Exploitability has not been
established for every match. No hostile resource-exhaustion test was run on the
laptop with a prior graphics crash. See `python-advisories.json` for descriptions,
IDs and package-specific fix versions; triage before changing packages.

### P2: sponsor readiness was overstated in some earlier descriptions

marimo works. Weave/Inference have optional code paths but no verified remote
transaction. ARIA has no working job/result bridge. CoreWeave has no verified
container deployment in this checkout. TypeSafe has no active implementation.
Capability text and static historical reports can overstate readiness: a file's
presence does not establish loadability, and a configured key does not prove an
export succeeded. Trace publication also lacks a durable external receipt/retry
workflow. See SPONSORS.md for exact wiring and completion checks.

### Release scope: local single workspace only

There is no tenant/account system, production identity, session-revocation endpoint,
public research-service boundary, rehearsed automated restore, or complete versioned
migration framework. The DB enables foreign keys, but domain ID columns do not all
have declared foreign-key constraints. Application checks carry those relationships.
These are reasons to keep the deployment scope local, not claims of exploited bugs.

### Scientific and licensing gates remain open

Kragel registration, scoring and transfer are unvalidated. TSAM execution is real
but its logits are experimental and uncalibrated. Quantization accuracy has not
been established against the original end-to-end pipeline. Non-commercial terms
require review before a commercial product. The Windows 0x113 crash root cause is
still unresolved; this audit proves one bounded inference completed, not that
arbitrary workloads cannot crash the driver.

## What was inspected and what was not

Reviewed source paths cover API/session boundaries, managed media operations,
MCP tool wiring, domain validation, worker/process lifecycle, actual inference,
cache/evidence publication, numerical readouts, edit selection, sponsor functions,
research data and browser flows. Regression tests exercise error and recovery
paths; browser checks deliberately delayed geometry and aborted a frame request.

This is a broad operational and source-backed readiness audit, not an exhaustive
penetration test, all-input proof, model malware scan, scientific benchmark or
native-driver audit. No paid sponsor job, public/cloud deployment or sustained GPU
stress test was performed. No credentials or drivers were changed. Dependencies
were inspected; the advisory tool ran in an isolated uv tool environment.

## Reproduce and inspect

- `scripts/audit_system.py`: new bounded MCP inference and all-record artifact checks.
  Each invocation intentionally creates a named audit project/composition.
- `scripts/verify_refinement.py`: temporary Edge acceptance tests.
- `.venv/Scripts/python.exe -m pytest backend/tests -q`: backend suite.
- `npm.cmd run build`, `npm.cmd audit --json` from `frontend`: build/advisories.
- `data/verification/system-audit/report.json`: concise machine-readable verdict.
- `runtime.json`: actual MCP, asset, array and output checks.
- `fresh-output.zip`: downloadable evidence, with the actual NumPy array.
- `browser.json`, `npm-audit.json`, `python-advisories.json`: tool receipts.
- `runtime-dependencies.txt`, `dependency-scope.json`: advisory input/scope snapshot.

All paths in the preceding evidence list are under
`D:/NeuroLoop/data/verification/system-audit` unless otherwise specified.
Current completed-run history includes earlier failures/cancellation; those were
retained rather than removed to make an all-green history.
