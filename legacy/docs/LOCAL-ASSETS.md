# Local asset handoff

`NeuroLoop 2` was a packaged copy of this same application. Its source files
match the GitHub checkout; the meaningful additions were local model weights,
scientific readout files, static cortical geometry and the pinned spaCy wheel.
Those files now live at the paths expected by the application in this
checkout.

## What is shared through Git

The verified static anatomy files under `data/geometry/` are allowed through
the root ignore rules so a fresh clone can render the anatomy view. Runtime
state such as the database, media, logs and `data/inference-quarantine.json`
remains local.

The multi-gigabyte model files remain intentionally ignored. GitHub’s normal
repository storage is not an appropriate transport for these licensed weights,
and the checkout does not have Git LFS configured. The local copies survive
ordinary `git pull` and do not appear in source commits. A partner who starts
from a fresh clone must receive the asset bundle separately or download the
pinned sources with the existing model scripts.

Do not place model files under `backend/`; that directory is only the Python
application package and tests. The application resolves all model paths from
the repository root.

## Verify this checkout

From the repository root, run:

```text
python scripts/verify_local_assets.py
```

The check is dependency-free and does not import or execute neural models. It
checks the downloaded model manifests, the TRIBE checkpoint, quantized video
weights, Whisper files, geometry, TSAM/Kragel assets and the spaCy wheel.

The copied quarantine file is deliberate: it preserves the existing
post-crash execution hold. It must not be deleted as a setup shortcut; saved
evidence and the web/API review workflow remain available while fresh model
execution is paused.

## Git hygiene

The root `.gitignore` now also excludes Finder metadata, Hugging Face cache
markers and downloader metadata. The stray `backend/config.json`,
`backend/config.json.metadata`, `backend/gitignore` and
`backend/CACHEDIR.TAG` were incomplete downloader artifacts, not application
configuration; they were removed from the checkout. The valid model config is
under `models/text/llama-3.2-3b-unsloth-q4/`.
