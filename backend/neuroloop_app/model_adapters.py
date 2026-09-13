"""Real, lazy model adapters for the shared notebook. No weights load on import."""
from __future__ import annotations

import gc
import json
from pathlib import Path

from .domain import ModelProvenance, digest
from .notebook import GeneratedFile
from .sponsors import ProviderFailure

H3_REVISION = "37794083e8693f7b328061d831c104e6351eef5d"
IDEOGRAM_REVISION = "ee79a7237b519f1402ceacf952f30c8a31ec5073"


def dimensions(aspect, long_edge, multiple=32):
    width, height = map(int, aspect.split(":"))
    scale = long_edge / max(width, height)
    return tuple(max(256, round(value * scale / multiple) * multiple) for value in (width, height))


def provenance(model, version, settings, **extra):
    return ModelProvenance(model=model, version=version, configuration_hash=digest({
        "adapter": "shared-notebook-v1", "long_edge": settings.model_long_edge,
        "steps": settings.model_steps, **extra}))


class H3Adapter:
    def __init__(self, settings):
        self.settings, self.runtime = settings, None

    @property
    def progress(self):
        return dict(self.runtime.progress) if self.runtime else {"phase": "Initializing MiniMax H3"}

    def __call__(self, ctx):
        ctx.check_cancelled()
        if set(ctx.parameters) - {"seed"}:
            raise ProviderFailure("INVALID_OUTPUT", "MiniMax sampling preset is operator-owned; generic controls are unsupported")
        duration = float(ctx.campaign["duration_seconds"])
        if not 2 <= duration <= 15:
            raise ProviderFailure("INVALID_OUTPUT", "MiniMax H3 supports 2–15 seconds in this profile")
        # Keep the parent and every original media reference. Documents are supplied
        # as extracted text to the planner, never passed to a media decoder.
        references = [a.path for a in ctx.references if a.kind in {"image", "video", "audio"}]
        if ctx.current_media and ctx.current_media.path not in references:
            references.insert(0, ctx.current_media.path)
        if self.runtime is None:
            from .h3_runtime import create_runtime
            self.runtime = create_runtime()
        width, height = dimensions(ctx.campaign["aspect_ratio"], self.settings.model_long_edge)
        # Use the three frame profiles exercised by the original notebook.
        # Preserve the requested duration through explicit retiming below.
        frames = 124 if duration <= 5.2 else 243 if duration <= 10.2 else 345
        output, metadata = self.runtime.generate(ctx.prompt, width=width, height=height,
            frames=frames, steps=self.settings.model_steps, seed=int(ctx.parameters.get("seed", 11)),
            reference_paths=references, output_dir=ctx.output_dir, cancelled=ctx.cancelled)
        ctx.check_cancelled()
        native_duration = float(metadata["duration"])
        if abs(native_duration - duration) > 0.02:
            import subprocess
            from imageio_ffmpeg import get_ffmpeg_exe
            exact = ctx.output_dir / "creative.mp4"
            subprocess.run([get_ffmpeg_exe(), "-y", "-i", str(output), "-vf",
                f"setpts={duration/native_duration}*PTS,fps=24", "-af",
                f"atempo={native_duration/duration},apad", "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-movflags", "+faststart", str(exact)], check=True, capture_output=True, timeout=120)
            output = exact
            metadata.update(duration=duration, retimed=True)
        return GeneratedFile(Path(output), metadata)

    def park(self):
        # Unload on model switches to avoid retaining two very large CPU models.
        if self.runtime:
            self.runtime.unload()
            self.runtime = None


class IdeogramAdapter:
    """The official checkpoint is text-to-image; it does not edit reference pixels."""
    def __init__(self, settings):
        self.settings, self.pipe = settings, None

    def __call__(self, ctx):
        ctx.check_cancelled()
        if ctx.current_media and ctx.conditioning != "text_alternative":
            raise ProviderFailure("UNAVAILABLE", "Ideogram 4 is text-to-image. Request a new alternative; it cannot edit the parent image.")
        # Never silently pretend image references were consumed by a text-only API.
        if any(a.kind in {"image", "video", "audio"} and (ctx.current_media is None or a.asset_id != ctx.current_media.asset_id) for a in ctx.references):
            raise ProviderFailure("UNAVAILABLE", "Ideogram 4 cannot consume media references. Use a text-only campaign or a reference-capable image model.")
        from .ideogram_caption import caption_json
        if set(ctx.parameters) - {"seed"}:
            raise ProviderFailure("INVALID_OUTPUT", "Ideogram sampling preset is operator-owned; generic controls are unsupported")
        try:
            caption = caption_json(ctx.prompt)
        except (ValueError, TypeError) as exc:
            raise ProviderFailure("INVALID_OUTPUT", "Ideogram requires a reviewed structured JSON caption") from exc
        import torch
        from ideogram4 import Ideogram4Pipeline, Ideogram4PipelineConfig, PRESETS
        from ideogram4.caption_verifier import CaptionVerifier
        issues = CaptionVerifier().verify_raw(caption)
        if issues:
            raise ProviderFailure("INVALID_OUTPUT", "Invalid Ideogram caption: " + "; ".join(issues))
        if not torch.cuda.is_available():
            raise ProviderFailure("UNAVAILABLE", "Ideogram FP8 requires the configured CUDA GPU host")
        if self.pipe is None:
            from huggingface_hub import HfApi
            # This SDK accepts a repo ID, not a local snapshot or revision.
            # Fail closed if its default branch differs from the tested revision.
            hub = HfApi()
            repo = "ideogram-ai/ideogram-4-fp8"
            if hub.model_info(repo).sha != IDEOGRAM_REVISION:
                raise ProviderFailure("UNAVAILABLE", "Ideogram checkpoint revision changed; validate the new revision before loading")
            self.pipe = Ideogram4Pipeline.from_pretrained(config=Ideogram4PipelineConfig(weights_repo=repo), device="cuda", dtype=torch.bfloat16)
            if hub.model_info(repo).sha != IDEOGRAM_REVISION:
                self.park()
                raise ProviderFailure("INVALID_OUTPUT", "Ideogram revision changed during loading")
            count = sum(type(m).__name__ == "Fp8Linear" for root in
                [self.pipe.conditional_transformer, self.pipe.unconditional_transformer, self.pipe.text_encoder] for m in root.modules())
            if not count:
                self.park()
                raise ProviderFailure("INVALID_OUTPUT", "Expected Ideogram FP8 layers")
        width, height = dimensions(ctx.campaign["aspect_ratio"], self.settings.model_long_edge, 16)
        preset = PRESETS["V4_TURBO_12"]
        images = self.pipe(caption, width=width, height=height, num_steps=preset.num_steps,
            guidance_schedule=preset.guidance_schedule, mu=preset.mu, std=preset.std,
            seed=int(ctx.parameters.get("seed", 11)))
        ctx.check_cancelled()
        output = ctx.output_dir / "creative.png"
        images[0].save(output)
        return GeneratedFile(output, {"width": width, "height": height, "preset": "V4_TURBO_12", "precision": "FP8 weights; BF16 activations", "reference_conditioning": False})

    def park(self):
        if self.pipe is None:
            return
        self.pipe = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def configure_models(registry, settings):
    """Registration is cheap. Settings explicitly select which loaders may run."""
    if settings.enable_h3:
        h3 = H3Adapter(settings)
        registry.register_generator("video", provenance=provenance("unsloth/MiniMax-H3-FP8", H3_REVISION, settings),
            loader=lambda: h3, park=h3.park, supports_regeneration=True)
    if settings.enable_ideogram:
        image = IdeogramAdapter(settings)
        registry.register_generator("image", provenance=provenance("ideogram-ai/ideogram-4-fp8", IDEOGRAM_REVISION, settings),
            loader=lambda: image, park=image.park, supports_regeneration=False, supports_media_references=False)
    if settings.vision_model and settings.wandb_api_key.get_secret_value():
        from .vision_adapter import VisionAdapter
        vision = VisionAdapter(settings)
        registry.register_evaluator("vision", provenance=vision.provenance, loader=lambda: vision)
    if settings.enable_legacy_evaluators:
        from .research_adapters import configure_research
        configure_research(registry, settings)
    return registry
