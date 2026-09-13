# Shared GPU notebook

The selected runtime for this project is the existing hosted Molab notebook. See [MOLAB_NOTEBOOK.md](MOLAB_NOTEBOOK.md) for its actual setup and connection limits. Do not use the user's local GPU. The installation instructions below are for separately provisioned hosts.

The current application is `backend/neuroloop_app`. The browser uses `/api/v2` through its authenticated Next.js proxy. NeuroLab claims jobs from the CPU API over outbound HTTPS; no extra inference web server is required.

## Install on your GPU host

Use a separate GPU environment. The earlier media studio was exercised with PyTorch 2.11 / CUDA 13.0 on a 96 GB RTX PRO 6000 Blackwell and approximately 160 GB system RAM. The extracted adapters still need a full execution test on the selected self-hosted machine. An ordinary laptop GPU is not a validated replacement.

```sh
python -m pip install 'torch==2.11.0' --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e '.[notebook,documents]'
python -m pip install -r notebooks/requirements-fp8.txt
# Install ffmpeg/ffprobe with your host's package manager.
python -m marimo edit notebooks/NeuroLab.py --host 127.0.0.1 --port 2718
```

Keep the notebook on loopback and access it through your authenticated host access or SSH forwarding. Configure the variables in `notebooks/self-hosted.env.example` using the host's secret store or the project `.env`. Do not copy the application's operator key into the worker; it needs its separate worker token only. Choose an available W&B text planning model and a vision-capable model explicitly. The vision adapter samples actual candidate and reference frames and validates the returned evidence schema.

Click **Start shared worker** in NeuroLab. Registration/import does not download weights. The first eligible job loads the requested model. The app's Connections & settings page reports worker heartbeats and registered capabilities; READY means registered, not execution-verified.

## Model behavior

| Model | Input and behavior |
|---|---|
| MiniMax H3 FP8 | Text plus image/video/audio references; parent media is retained for regeneration. Original media limits apply: 9 images, 3 videos, 3 audio files, 12 total; total reference video duration ≤15 seconds. Output is explicitly retimed to the requested 2–15 seconds. |
| Ideogram 4 FP8 | Text-to-image, Turbo 12. Media references are rejected before weights load. Later rounds can create **text alternatives** from planner/evaluation evidence; lineage remains attached but they are not pixel edits. The SDK's default revision is checked before and after load. |
| W&B vision | Real image bytes / six sampled video frames, plus reference previews. Sparse sampling cannot verify all video/audio content; unknown constraints must remain UNKNOWN. |
| TSAM | Existing original audiovisual evaluator in an isolated subprocess. Requires its source, checkpoint, research dependencies and research-license acknowledgement under `NEUROLOOP_RESEARCH_ROOT`. Preserves logits and limitations without inventing a quality probability. |
| TRIBE v2 | Existing original evaluator in an isolated subprocess. Requires its checkpoint, encoders, geometry, dependencies and preprocessing assets under the same research root. Preserves real fsaverage5 values and timestamps. Existing execution holds remain enforced. Static-image presentations are disabled. |
| W&B planner / TypeSafe | Existing typed planning and decision clients. Code continues to enforce candidate limits, constraints, leases and human review. |

Install TSAM/TRIBE assets using the preserved `models/README.md` and setup scripts on the GPU host. They are not bundled or silently downloaded by this notebook. An absent checkpoint leaves that evaluator unregistered. Do not copy old application credentials or databases to make a research adapter work.

## Memory, idle and timing

Jobs are serialized. H3 keeps CPU weights between consecutive jobs and offloads GPU weights after generation. Ideogram stays loaded between consecutive image jobs, avoiding its previous process/reload on every image. Switching model families unloads their owned weights. After five minutes without eligible work, the worker stops and releases model memory; restarting is an explicit notebook action. Cancellation is cooperative; H3 checks between denoising steps, while the current Ideogram SDK cannot interrupt an in-flight call.

**Stopping a worker does not shut down or stop billing for the GPU host.** Stop/suspend the host through its provider when finished. Neither two-minute generation nor 2K memory fit is established for the new host. Cold downloads and model switching can take much longer than a warm generation.

The Unsloth support files retain their AGPL-3.0-only notices and license in `backend/neuroloop_app/h3_support`. Model access/license requirements remain with their upstream providers.

## Connect your software

The CPU API is the integration point: `GET /api/v2/capabilities`, `POST /api/v2/campaigns`, multipart `POST /api/v2/campaigns/{id}/assets`, and `POST /api/v2/campaigns/{id}/runs` with an `Idempotency-Key`. Poll `GET /api/v2/runs/{id}` for job state and output asset IDs; fetch `/api/v2/assets/{id}/content` for media and `/api/v2/runs/{id}/export` for evidence. Schema and request bodies are in the running API's `/docs`.

Use application authentication over HTTPS from your server. Keep long-lived keys out of browser code; the bundled Next.js UI exchanges operator/local bootstrap access for an HttpOnly session cookie. The research MCP entry point remains `neuroloop_app.mcp_server` with its restricted agent credential. A worker key cannot act as an operator or approve deployment.
