# Molab research notebook

`http://localhost:2718/` is the local marimo research app. It is not the hosted Molab service. Molab is the marimo team's hosted notebook workspace at https://molab.marimo.io/notebooks.

## Portable notebook

`research/molab_review.py` is a standalone CPU-only marimo notebook. It requires Python 3.11+, marimo 0.24+, pandas 2.2+ and Plotly 6+. Its inline dependency block supports isolated notebook execution. It does not import NeuroLoop backend code, connect to a database, request API credentials or launch inference.

Upload `artifacts/molab/neuroloop-evidence.json` in the notebook's file control. The file is an allowlisted export of actual historical verification data plus a fresh TSAM CPU output, not sample data. It contains 24 historical runs, 7 interventions, 29 cortical evaluations and one fresh TSAM five-second window. The live workspace was reset separately; this evidence is historical and must not be represented as new live projects.

The export omits project/asset names, raw database IDs, timestamps, briefs, paths, transcripts, media and credentials. Export-local run/context aliases preserve chart joins. Numerical cortical means are model predictions rather than measurements from an identifiable person.

## Eleven views

1. Baseline versus candidate similarity: evaluate whether an intervention improved its objective.
2. Operator outcome counts: kept, reverted and rejected work.
3. Search trajectory: scores within each run, including failed candidates.
4. Parallel coordinates: inspect gain alongside whole-run cost; costs repeated across interventions must not be summed.
5. Compute efficiency: evaluations versus recorded seconds, including failed runs.
6. Recorded run outcomes: operational counts, not a hardware reliability estimate.
7. Operator experience: context-scoped observations, not held-out policy improvement.
8. Cortical hemisphere timeline: select an actual saved evaluation.
9. Cortical hemisphere heatmap: signed units and symmetric per-evaluation color limits.
10. TSAM class logits: eight actual uncalibrated outputs from the fresh CPU pass.
11. TSAM coverage: five evaluated seconds and one omitted incomplete second.

The notebook also includes sortable run/intervention tables, provenance, chart interpretation and explicit scientific limits. No simulated rows are generated when data is absent.

## Verification

- `python -m marimo check --strict research/molab_review.py` passed.
- Programmatic `app.run` with the exported file loaded all records and rendered 10 output cells without exception.
- `artifacts/molab/evidence-preview.html` is a standalone Plotly preview with 11 charts. It bundles the plotting library; opening it makes no sponsor/API calls.
- `artifacts/molab/notebook-verification.json` records the verification status.

## Hosted notebook — created and browser verified

Open [NeuroLoop / Evidence review](https://molab.marimo.io/notebooks/nb_B79BrKA5Rh4UNJxj9NQ1kf) in Jerry's signed-in Molab workspace.

The user completed sign-in. Browser file import was unavailable because extension file-URL access was disabled, so the reviewed Python code and sanitized numerical JSON were pasted directly into the notebook editor. The source is preserved locally in `artifacts/molab/hosted-cell.py`. Save and Preview were used in the actual Molab page.

The hosted version embeds the sanitized verification snapshot and displays 11 chart tabs plus tables. Its initial hemisphere views show evaluation-001; all 29 numerical records remain available in the expandable record section. The portable `research/molab_review.py` instead accepts a new JSON upload and provides an evaluation selector. These are intentionally different entry mechanisms for the same actual evidence.

The notebook executed on the default **4 CPU / 32 GiB** configuration. No GPU allocation, model download, sponsor inference call, public sharing or paid compute upgrade was requested. The browser verified rendered baseline/candidate points, switched to interactive Parallel Coordinates and then to the actual TSAM logits. `artifacts/molab/molab-tsam-verified.png` captures the hosted output. The bottom notebook error counters showed zero.

For future file uploads, enable **Allow access to file URLs** for the ChatGPT browser extension in Edge settings, or manually import the portable notebook and JSON. This permission is not required to view the saved hosted snapshot.

## Boundaries

The fresh TSAM check returned eight finite logits on a six-second audiovisual input in approximately 4.422 seconds using CPU. The model evaluated only the complete first five-second window. No observed viewer labels or domain calibration were available. This establishes executable model wiring, not emotional accuracy.

Historical TRIBE charts do not establish post-crash GPU stability. Higher similarity scores do not demonstrate click-through rate, purchases, human preference or self-healing hardware. Weave trace export and W&B experiment records are independent integrations; this notebook does not call them.
