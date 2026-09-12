# NeuroLoop partner setup

This is the GitHub checkout for the shared NeuroLoop application. The static
anatomy geometry is included in Git; the large licensed model weights are
intentionally kept outside Git and must be copied separately into the same
repository-root paths. Once copied, the companion `NeuroLoop 2` folder is no
longer needed.

## Windows setup

1. Install Python 3.11, `uv` and Node.js with npm.
2. From this repository root, run `python Setup-Partner.py`.
3. Copy or obtain the local model bundle, then run
   `python scripts/verify_local_assets.py`.
4. Start the application with `Start-NeuroLoop.cmd`.

The setup creates isolated runtimes, a private local authentication secret and
the frontend build. It does not run GPU inference or enable sponsor services.
The copied `data/inference-quarantine.json` preserves the existing post-crash
execution hold; do not remove it as a setup shortcut.

## Git workflow

The repository root is the only Git working tree. Pull and push source changes
from here as usual. Model weights, runtime output, credentials, cache markers
and Finder metadata are ignored, so they remain on the machine and do not
create merge conflicts. Do not force-add files from `models/`, the model
checkpoint directory or runtime `data/`.

Read [the local asset handoff](docs/LOCAL-ASSETS.md) for the exact asset list,
verification boundary and licensing/runtime notes.
