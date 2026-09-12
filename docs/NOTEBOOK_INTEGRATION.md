# Connect all models in the same notebook

Install the package in the notebook environment, not the old V1 app runtime. `notebooks/NeuroLab.py` is the shared execution and research entry point. Merely opening it does not download or invoke a model.

## Required secrets/settings
- `NEUROLOOP_PUBLIC_API_URL`: approved CPU API HTTPS origin. Remote compute cannot use a laptop's loopback address.
- `NEUROLOOP_WORKER_TOKEN`: copy this one worker credential securely from the application's secret manager. Never give the notebook an operator/root or human-session token.
- `WANDB_API_KEY`, `WANDB_PROJECT=entity/project`, `NEUROLOOP_INFERENCE_MODEL`: an actually available W&B Inference model.
- `TYPESAFE_API_KEY`; optional `NEUROLOOP_TYPESAFE_MODEL` (default `jev-latest`).
- `NEUROLOOP_PROVIDER` and affirmative `NEUROLOOP_PROVIDER_WORKLOAD_APPROVED` when the provider requires workload permission. This flag is an operator attestation, not a bypass.
- Optional `NEUROLOOP_RESEARCH_TOKEN`: restricted agent token for analysis reads. A worker token cannot read all campaigns or approve deployment.

## Generator contract

```python
from neuroloop_app.notebook import GeneratedFile, ModelRegistry
from neuroloop_app.domain import ModelProvenance

# loaded_video_callable is YOUR real model wrapper, not a NeuroLoop fake model.
registry.register_generator(
    "video",
    provenance=ModelProvenance(model=actual_model_id, version=actual_checkpoint_revision,
                              configuration_hash=actual_configuration_hash),
    loader=lambda: loaded_video_callable,
    supports_regeneration=True,
    park=offload_video_components,
    activate=restore_video_components,
)
```

Use `image` for the image model. Loader returns `Callable[[GenerationContext], GeneratedFile]`. Within that callable use `ctx.prompt`, `ctx.edit_intent`, `ctx.references`, **`ctx.current_media` for regeneration**, and `ctx.parameters`; write the result in `ctx.output_dir`. Return `GeneratedFile(path=actual_output_path, parameters=actual_parameters, cost_usd=known_actual_cost_or_None)`. Check `ctx.check_cancelled()` before, during supported model steps, and after execution. Do not register regeneration support unless your real wrapper consumes the previous media and references.

The registry accepts any genuine model wrapper with this contract. It deliberately does not invent MiniMax/Ideogram Python function names or assume their checkpoints fit. If the image model is an API rather than local weights, its real API call can be executed from this same notebook adapter.

## Evaluator contract

`register_evaluator("vision"|"tsam"|"tribe", provenance=..., loader=lambda: real_callable)`.

Callable receives `EvaluationContext`: creative media, original references, campaign/brand specification, required constraint names, cancellation and output directory. Return `EvaluationOutput(result=EvaluationResult(...), artifacts=[actual_output_paths])`.

Vision must return `creative_quality` with score provenance and real checks for `product_identity`, `approved_claims_only`, `no_prohibited_claims`, plus every requested locked requirement. Unverified requirements are UNKNOWN, not PASS. Preserve evaluator configuration/version for comparisons. TSAM/TRIBE must include explicit scientific limitations. No evaluator may invent CTR, conversions, viewer measurements or unavailable scores.

For Brain Lab, `write_cortical_artifact(output_path, actual_values, actual_times)` writes finite frames × 20484 fsaverage5 arrays. Native TRIBE output must be mapped with a technically valid surface mapping before this call; do not resize/reshape arbitrary tensors to make them fit. Include the real file in EvaluationOutput.artifacts. Raw summaries/ROI features can remain in typed observations with provenance.

## GPU scheduling and lifecycle

All registered models share one queue/registry lock. Load lazily once, keep warm when feasible, or park components between jobs to fit memory. No automatic model eviction guess is made. `worker.start()` is an explicit notebook action; `worker.stop()` requests cooperative stop. A blocking CUDA operation may not be immediately cancellable; hard enforcement requires provider/process resource controls.

Keep `notebook-cache` on durable storage when possible. Generated/result JSON journals reconcile completed work after restart without repeating inference. Do not edit receipt files while a worker is active. Unit-test fixture callables are never imported into this notebook.
