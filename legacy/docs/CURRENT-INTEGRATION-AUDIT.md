# Current integration audit — September 11, 2026

Historical snapshot: this section records the earlier read-only inspection. For subsequent fresh CPU model runs and fixes, see [fresh execution verification](FRESH-EXECUTION.md). It records the ledger before the user-requested workspace cleanup. Model execution was paused throughout this audit.

## What the sponsor pages are

| Surface | What it does in NeuroLoop | Evidence checked now |
|---|---|---|
| [Local marimo](http://localhost:2718/) | Python research application reading the same SQLite ledger and saved cortical summaries as the website | HTTP 200; `research/lab.py` opens SQLite with `mode=ro` |
| [Molab](https://molab.marimo.io/notebooks) | Hosted marimo notebook environment and examples; separate from our local application | No claim that NeuroLoop data was uploaded there |
| [W&B project](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop) | Project container for experiment metadata, artifacts and traces | Existing project used by the integration |
| [W&B table](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/table) | Rows of W&B runs, their configuration, state and numerical summaries | Historical Launch failure remains a failure, not successful optimization |
| [Weave traces](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/traces) | Execution spans with IDs, timing and selected numerical evidence | Five locally delivered receipts; two specific ended calls independently read back using the official W&B MCP during this audit |

The independently read-back calls were [saved evaluation audit](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/1c6d3e1b-1a09-4eae-b6a8-84490afff8c6) and [interrupted run](https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/calls/eb0aae3a-6fa9-5dee-9a3e-d403f9fa9e02). An ended trace means its record exists, not that the associated experiment succeeded. Trace metadata is not a token-billing measure for local TRIBE.

Weave is useful for inspectable provenance; marimo is useful for exploring results. ARIA has provided an actual review and hypothesis. Its local Launch bridge has not completed acceptance after the graphics crash. W&B Inference, CoreWeave compute/storage, TypeSafe, Ideogram and MiniMax generation are not functioning integrations in this installation. A logo or connection configuration is insufficient proof.

## The actual plots

`research/charts.py` implements seven experiment views, plus cortical timeline/heatmap helpers. The notebook displays recorded runs, interventions, compute cost, saved hemisphere timelines, operator statistics and the seven experiment views. The follow-up UI work wired the hemisphere heatmap into a second saved-evaluation tab with a symmetric zero-centered scale and explicit units. Each experiment chart now includes a short interpretation and limitation. Empty and malformed cortical summaries are shown as unavailable rather than fabricated.

| View | Useful question | Interpretation limit |
|---|---|---|
| Baseline versus candidate scatter | Did this edit raise the fixed reference score? | A higher score is not measured preference |
| Stacked operator outcomes | Which operators were kept or reverted? | Small, selected sample |
| Search trajectory | How did candidates change within a run? | Candidate score is not necessarily accepted-best score |
| Parallel coordinates | Which score/cost combinations deserve inspection? | Cost is whole-run, repeated for each intervention |
| Compute efficiency scatter | How much work did completed and failed runs consume? | Interrupted compute accounting may be partial |
| Run reliability bars | How many runs completed, failed or cancelled? | These are statuses, not a measured hardware reliability rate |
| Operator experience scatter | What has the local policy observed in each context? | No held-out evidence of policy generalization |
| Hemisphere timeline | How do saved predicted responses change over the stimulus? | Segment start time is stimulus timing, not inference latency or an emotion probability |

Professional use means choosing a question and showing its units, provenance and limits, rather than adding charts for their own sake. With only seven recorded interventions, a dramatic performance dashboard would overstate the evidence.

## Live MCP evidence

The current conversation successfully called `get_capabilities`, `get_system_status`, `get_research_ledger` and `get_external_receipts` through the actual NeuroLoop MCP connection. The official W&B `query_weave_traces_tool` also returned the two named remote calls. No GPU or model-loading tool was used.

At this snapshot the ledger contained **24 runs, 7 interventions, 29 evaluations and 5 policy-statistic rows**. The latest saved TRIBE evaluation was `ead079b9-23d7-497f-bfd1-baa9ddcd0491`. These are historical persisted records, not newly generated results. Long-lived MCP processes may retain pre-merge imported code: restart/reload a client after backend changes and compare fresh-process capabilities before treating conflicting statuses as asset failures.

## TSAM: present and wired, experimental

The requested [TSAM repository](https://huggingface.co/dnamodel/tsam-viewer-emotions) is the model used here; [Adcumen](https://huggingface.co/datasets/dnamodel/adcumen-viewer-emotions) is the associated dataset, not another inference model. Files are under `models/emotion/tsam/`. Both checkpoint SHA-256 values were recomputed in this audit:

```text
tsam_weights.tar     f3a5e228ef12e9b9bf19116928392e8ed486f2d1908fea5c93e9452c62841569
backbone_weights.tar c3df9a6f26e0d4b62dab34da56371ee313f298c6988dee50be95a03803d78db8
```

`backend/neuroloop/tsam.py` implements CPU-only strict loading of the composite network; `load_state_dict(..., strict=True)` applies to every expected checkpoint section. The local source revision is `890540450e9459b9f917b2c50204b5be6fe72433` from [the authors' code](https://github.com/gmontana/DecodingViewerEmotions). This audit inspected loading code but did not execute a fresh model load or forward pass.

The current HF card describes seven classes, while the pinned `setup_data.py` lists **eight**, including Neutral; our adapter follows the eight-class code/checkpoint contract. That discrepancy must remain explicit. The adapter uses complete five-second audiovisual windows and omits incomplete tails. Output logits and ensemble-normalized values are uncalibrated relative evidence. Held-out reproduction, class-mapping confirmation, leakage review and target-domain calibration remain required. The upstream card restricts use to academic research/non-commercial evaluation.

## Kragel: assets and a projection adapter are present

All **37 files** in the local download manifest were rehashed and matched, including the seven HDR/IMG signature pairs, surface files and license. The source is [CANlab Neuroimaging Pattern Masks](https://github.com/canlab/Neuroimaging_Pattern_Masks), revision `107a4f18d80c0c2ea5ac0ae3ccf3398a80cad504`; local path `models/brain_readouts/kragel2015/source/`.

`backend/neuroloop/kragel.py` uses the volume maps and four fsaverage5 white/pial geometry files. It samples five depths through each cortical ribbon, orders left then right, and tracks geometry, volume and projection hashes. It does not resize the published 32,492-vertex surface arrays to 10,242 vertices. Live capabilities reported `experimental_ready`, `missing=[]`, `validation=unvalidated`.

**Registration is not established by that status.** `_sample_volume` directly applies the inverse volume affine to fsaverage geometry coordinates. The inspected adapter does not apply an independently documented fsaverage-to-MNI registration transform. Valid interpolation, complete coverage and finite scores cannot prove anatomical alignment. Reproduce reference scoring, verify coordinate conventions and registration landmarks, then evaluate transfer from measured fMRI to TRIBE predictions before making emotion claims.

`response.py` contains an explicit 0.55 TSAM / 0.45 Kragel ensemble for supported dimensions. These weights and the amused/content-to-happiness mapping are design choices, not empirically validated fusion. Agreement does not validate either component.

## Honest assessment of the loop

There is real engineering beyond a wrapper: fixed objectives, bounded edit operators, preserved originals, acceptance/revert decisions, context-scoped policy statistics, persisted evidence, cancellation, crash holds and remote receipts. The local models stay frozen. This is an evidence-tracked search loop; it is not model self-training.

Self-improvement is limited to operator selection statistics and accepted artifacts against the chosen proxy. Generalization requires equal-budget fresh-versus-experienced policy tests on unseen briefs. Self-healing currently means preserving results and failing closed after interruption, not repairing a graphics driver or autonomously recovering a validated scientific workflow. The latest full ARIA/Launch experiment crashed. Do not claim production stability or autonomous end-to-end research success from the earlier successful runs.

The supplied ten-thumbnail video example is hypothesis-generating only. Its stated correlation was not reproduced here. Views are affected by topic, title, exposure, age and audience, and selecting five high/five low examples biases the sample. Predicted response magnitude alone does not identify cognitive load, attractiveness, or causal effects on views. A larger preregistered held-out study and controlled thumbnail testing would be needed. Meta's [demo](https://aidemos.atmeta.com/tribev2) was subsequently inspected in Edge: Examples/Performance/In-Silico/Multimodality, True/Compare/Predicted, Open/Close, Normal/Inflated, and a media timeline are present. Its ground-truth comparison must not be represented as available for arbitrary NeuroLoop uploads without matched measured data.

## Documentation corrections and boundaries

Older `verification.json`, compatibility reports, and merged install-later language refer to earlier states or a code-only checkout. They do not describe this disk. Assets present, source implemented, successful loading, successful inference and scientific validation are separate states. This audit establishes the first two plus current MCP/remote receipt access; it does not close the inference or scientific release gates.
