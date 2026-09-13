# H3 quality investigation — 2026-09-13

The real browser test created run `b9c916d2-38d4-4183-976b-04c1bee40af2`.
It reached PLANNING with a queued PLAN job and verified Weave links, but the
notebook worker was offline. This is not a completed ad loop.

The generation notebook previously defaulted to four sampling grid points,
1024 × 672, and an enabled saved cat reference. The live form now starts with
the saved cat reference disabled, 1344 × 768, 124 frames, and 20 grid points.
The backend sampling default and environment examples now also use 20.

A real text-only desktop lamp advertisement completed in the hosted notebook
using those settings and seed 11: 124 frames, 5.1667 seconds, 247.7 seconds
inference, 379.46 seconds loading/preparation, 628.53 seconds through export,
77.78 GB peak allocated GPU memory. Playback showed a stable lamp silhouette
and a turn-on transition. An inspected frame from the older uploaded laptop
advertisement showed doubled contours; this is not a controlled A/B comparison.
The notebook result panel now displays the actual generation metadata beside
the video and download control. Existing outputs have not been overwritten.
The latest completed output now survives changes to the transient submission
future, instead of reverting to the historical cat clip. The live notebook
worker Settings explicitly use 20 steps as well.

GLM-5.3-Flash reviewed six actual sampled frames: visual quality proxy 0.88,
shape stability 0.93, ghosting freedom 0.92. These are model judgments, not
validated advertising outcomes. Brand identity remained UNKNOWN without a
reference. Sparse frames cannot verify complete motion or audio.

The exact MP4 upload was checked through W&B SDK file readback and played in
the W&B browser player. The Weave dataset was also read back.

- [Video and metrics](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/runs/h3-quality-27ad8a7926db2a87)
- [GLM evidence dataset](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/objects/neuroloop-h3-quality-verification/versions/l8YbrKGBCAex2ef3YGK9JzgC0hqqgzq8oCoohrRp4FM)

The full web loop remains blocked by the offline worker connection. No completed
campaign loop, TypeSafe approval, or TRIBE/TSAM evaluation of this new clip is
claimed by this standalone quality verification.

FP8 alone has not been established as the cause of the reported distortion.
Changing the prompt, references, resolution and sampling together tests a
better baseline, not an isolated causal comparison.

Primary references:

- [Diffusers H3 documentation](https://github.com/huggingface/diffusers/blob/main/docs/source/en/api/pipelines/minimax_h3.md): trained canvas 1344 × 768; sampling steps count grid points including terminal zero, so four points mean three model evaluations.
- [Unsloth FP8 model card](https://huggingface.co/unsloth/MiniMax-H3-FP8): text examples use eight steps; reference comparisons use twenty. Its divergence metrics are not quality scores.

Validation: `python -m pytest tests/test_notebook_models.py -q` — 9 passed.
These CPU contract tests do not establish GPU visual quality.
