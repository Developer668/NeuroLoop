# Existing Molab notebook

The selected GPU runtime is [the existing Molab notebook](https://molab.marimo.io/notebooks/nb_hmqbzUN6NR96sCQ55RKPXb). Do not run inference on the user's local GPU. Local application development and CPU tests are separate from hosted model execution.

The notebook contains a versioned source bundle and a shared NeuroLoop registry connected to the existing MiniMax H3 FP8 and Ideogram 4 FP8 studio functions. Its multi-file video controls are preserved. Ideogram is text-to-image and rejects media conditioning; it cannot edit reference pixels.

Models load on demand. Consecutive Ideogram images reuse the loaded model for five minutes. Switching to video or releasing models unloads it. Memory release does not stop provider billing: shut down the Molab session when finished. Save generated results before shutdown.

W&B planner/vision and TypeSafe configuration is read from private notebook secrets. Never put credentials in cells, exports, or this repository. TSAM and TRIBE remain unavailable without their actual checkpoints and required research assets.

## Application connection

The external application is not connected merely because the notebook's registry shows READY. READY identifies a registered callable, not a successful generation or a worker heartbeat.

The current local API address cannot be reached from Molab as `localhost`. A permitted connection requires an approved HTTPS application API, its separate worker credential, and provider permission for the workload. The notebook does not expose a public inference service and must not bypass the provider approval check.

Use the notebook's NeuroLoop status controls to inspect actual capabilities and worker state. Interactive generation inside the studio remains separate from a complete externally driven campaign loop.

The generic installation instructions in [SELF_HOSTED_NOTEBOOK.md](SELF_HOSTED_NOTEBOOK.md) apply to separately provisioned hosts; they are not a request to use the user's computer GPU.
