# Isolated local runtimes

The original `.venv` directories are preserved. Replacements live under
`.runtimes/app`, `.runtimes/model`, and `.runtimes/wandb-mcp`; none inherits system
packages. Inputs and resolved versions are under `infrastructure/runtime`.

The model runtime contains two explicit local packaging forks, not an unmodified
upstream dependency solution:

- `infrastructure/vendor/tribev2`: the existing official source, with dependency
  bounds changed to the locally exercised Torch 2.11 / torchvision 0.26 / NumPy
  2.4.6 stack. No neural weights or inference implementation changed here.
- `infrastructure/vendor/moviepy`: upstream v2.2.1, commit
  `f515b100e1fd069da6f29d5b01b1d42b52d8068d`, with local version
  `2.2.1+neuroloop.1` and Pillow bound 12.3–12.x. This permits the security-patched
  parser. Inference/media verification is required before activating this runtime;
  it does not establish every MoviePy feature is compatible.

The exploratory `model-overrides.txt` is not used by the final model lock. The
final resolver has no override flag; `uv pip check` must pass with the explicit
fork metadata. The upstream licenses remain alongside both sources.

Setuptools 81.0.0 meets PyTorch's `<82` dependency. Advisory
`CVE-2026-59890` / `PYSEC-2026-3447` affects Unicode manifest exclusions when
building/publishing source distributions on normalization-preserving filesystems.
This Windows inference runtime does not build or publish source distributions.
Build environments are separate; application and MCP runtimes use setuptools 84.
This is a scoped non-applicability assessment, not a claim that setuptools 81 is
universally patched. Reassess before packaging on macOS or publishing sdists.

Run `uv pip sync infrastructure/runtime/app.lock --require-hashes --python
.runtimes/app/Scripts/python.exe`. The model lock also needs the committed local
forks and the CUDA 12.8 wheel index (`--torch-backend cu128`). Model weights are
separate immutable recovery inputs; do not download alternate quantizations.

## Current model assets and advisory caveats

The model lock now includes `infrastructure/wheels/en_core_web_lg-3.8.0-py3-none-any.whl`, fetched from the official spaCy GitHub release by `scripts/fetch_runtime_assets.py`. SHA-256: `293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63`. It is installed in both model environments. Missing language assets are detected before GPU model work; an implicit upstream download previously stalled the first Launch attempt. Model profile IDs now include spaCy and language-model versions. Feature caches are separated by the model lock hash.

Accelerate1.13.0 matched `PYSEC-2026-3804` / `CVE-2026-69112` / `GHSA-4j2p-28q2-5m79`. The scan reported no fixed version. `backend/neuroloop/checkpoints.py` validates checkpoint shard maps before the local loader proceeds: missing, absolute, drive-qualified, traversal and escaping/non-file paths are rejected. This constrains this application's entrypoint; it does not patch every Accelerate loading API. Seven checkpoint tests exercise this boundary.

All five isolated environments passed `uv pip check` after recovery: app110/model192/W&BMCP121/app-rehearsal110/model-rehearsal192 packages. App-rehearsal runs the backend tests. Model-rehearsal decoded, resized, encoded and decoded a real NASA media clip using MoviePy2.2.1+neuroloop.1/Pillow12.3/NumPy2.4.6. Full second-model inference has not passed because the primary audiovisual repetition crashed Windows. The current execution hold remains active.

Package scans skip some local versions and CUDA wheel identifiers. Native binaries and source forks require separate review. A compatible dependency resolver and zero app advisory count are not comprehensive security certification.
