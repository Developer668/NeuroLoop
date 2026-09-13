"""Bridge the preserved TSAM/TRIBE implementations into typed notebook jobs.

The legacy evaluator runs in an owned subprocess: its offline Hugging Face flags,
model globals and independent configuration cannot leak into H3/Ideogram jobs.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from .domain import EvaluationResult, ModelProvenance, digest
from .notebook import EvaluationOutput, write_cortical_artifact
from .sponsors import ProviderFailure


class ResearchAdapter:
    def __init__(self, name, settings, checkpoint):
        self.name, self.settings, self.checkpoint = name, settings, checkpoint
        self.signature = (checkpoint.stat().st_size, checkpoint.stat().st_mtime_ns)
        self.provenance = ModelProvenance(model="TSAM" if name == "tsam" else "TRIBE v2",
            version="preserved-neuroloop-evaluator-v1", configuration_hash=digest({
                "checkpoint": str(checkpoint.relative_to(settings.research_root)), "stat": self.signature,
                "static_presentation": False, "include_kragel": name == "tribe", "adapter": "isolated-research-v2"}))

    def __call__(self, ctx):
        ctx.check_cancelled()
        if (self.checkpoint.stat().st_size, self.checkpoint.stat().st_mtime_ns) != self.signature:
            raise ProviderFailure("INVALID_OUTPUT", "Research checkpoint changed; rebuild the registry before comparison")
        limitations = ["Research model proxy, not observed viewer emotions, individual brain activity, or commercial outcomes."]
        if ctx.asset.kind != "video" or (self.name == "tsam" and not ctx.asset.details.get("has_audio")):
            return EvaluationOutput(EvaluationResult(evaluator=self.name, status="NOT_APPLICABLE",
                provenance=self.provenance, limitations=limitations,
                observations={"reason": "Requires video" + (" with audio" if self.name == "tsam" else "; static-image presentation is not enabled")}))
        folder = self.settings.research_root / "data" / "notebook-jobs" / ctx.job_id
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / ("input" + ctx.asset.path.suffix)
        shutil.copyfile(ctx.asset.path, source)
        request = folder / "request.json"
        request.write_text(json.dumps({"evaluator": self.name, "path": str(source), "kind": ctx.asset.kind,
            "details": {**ctx.asset.details, "duration": ctx.asset.details.get("duration_seconds")}, "output": str(folder / "result")}), encoding="utf-8")
        root = self.settings.research_root
        module_paths = [Path(__file__).resolve().parents[1], root / "backend",
                        root / "infrastructure/vendor/tribev2", root / "infrastructure/vendor/moviepy", root]
        env = dict(os.environ, NEUROLOOP_ROOT=str(root),
            PYTHONPATH=os.pathsep.join(str(path) for path in module_paths),
            NEUROLOOP_TSAM_ENABLED="true",
            NEUROLOOP_TSAM_RESEARCH_LICENSE_ACCEPTED=str(self.settings.tsam_research_license_accepted).lower(),
            NEUROLOOP_AUTH_TOKEN=secrets.token_urlsafe(32))
        with (folder / "process.log").open("wb") as log:
            process = subprocess.Popen([sys.executable, "-m", "neuroloop_app.research_process", str(request)],
                env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                while process.poll() is None:
                    ctx.check_cancelled()
                    time.sleep(.25)
                if process.returncode:
                    raise ProviderFailure("UNAVAILABLE", "Research model execution failed; inspect its private notebook process log")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        report = json.loads((folder / "result" / "report.json").read_text())
        artifact = ctx.output_dir / (self.name + "-report.txt")
        artifact.write_text(json.dumps(report, indent=2), encoding="utf-8")
        artifacts = [artifact]
        if self.name == "tribe":
            import numpy as np
            values = np.load(folder / "result" / "prediction.npy", allow_pickle=False)
            artifacts.insert(0, write_cortical_artifact(ctx.output_dir / "cortical.npz", values, report["times"]))
        return EvaluationOutput(EvaluationResult(evaluator=self.name,
            status="NOT_APPLICABLE" if report.get("status") == "not_applicable" else "SUCCEEDED",
            provenance=self.provenance, observations=report,
            limitations=report.get("limitations") or limitations), artifacts)


def configure_research(registry, settings):
    checkpoints = {
        "tsam": settings.research_root / "models/emotion/tsam/weights/tsam_weights.tar",
        "tribe": settings.research_root / "tribev2-balanced-qv-local/best.ckpt",
    }
    for name, checkpoint in checkpoints.items():
        if not checkpoint.is_file() or (name == "tsam" and not settings.tsam_research_license_accepted):
            continue
        adapter = ResearchAdapter(name, settings, checkpoint)
        registry.register_evaluator(name, provenance=adapter.provenance, loader=lambda adapter=adapter: adapter)
