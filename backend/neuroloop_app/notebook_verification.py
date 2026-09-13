"""Verify existing generated media in the notebook and publish attributed receipts.

This diagnostic path does not advance or bypass the campaign policy state machine.
"""
import hashlib
import json
from pathlib import Path
import traceback
from uuid import UUID
from .notebook import EvaluationContext, LocalAsset, atomic_json
from .vision_adapter import VisionAdapter


def evaluate_ads(worker, specs, campaign, folder):
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        identity = str(UUID(spec["id"]))
        status = root / (identity + "-status.json")
        try:
            atomic_json(status, {"state":"RUNNING","model":worker.settings.vision_model,"asset":identity})
            response = worker.client.get("/api/v2/assets/" + identity + "/content")
            response.raise_for_status()
            path = root / Path(spec["name"]).name
            path.write_bytes(response.content)
            sha = hashlib.sha256(response.content).hexdigest()
            if sha != spec["sha256"]:
                raise ValueError("Input media checksum changed")
            asset = LocalAsset(identity, path, spec["kind"], spec["mime"], sha, spec["details"])
            ctx = EvaluationContext("ad-vision-" + identity, identity, campaign, asset, [],
                ["no_unsubstantiated_performance_claims", "legible_brand"], root, lambda: False)
            result = VisionAdapter(worker.settings)(ctx).result.model_dump(mode="json")
            atomic_json(root / (identity + "-result.json"), result)
            metadata = {"input_asset_id":identity,"input_sha256":sha,"source_receipt":"ad-vision-"+identity,
                        "source_kind":"generated_ad_evaluation","title":"GLM vision — " + spec["name"],"result":result}
            response = worker.client.post("/api/v2/workers/evidence", data={"metadata":json.dumps(metadata)})
            response.raise_for_status()
            atomic_json(status, {"state":"SUCCEEDED","model":worker.settings.vision_model,"receipt_id":response.json()["id"]})
        except Exception as exc:
            atomic_json(status, {"state":"FAILED","error_type":type(exc).__name__,"code":getattr(exc,"code",None),
                "detail":getattr(exc,"detail","Inspect the private notebook error log")})
            (root / (identity + "-error.txt")).write_text(traceback.format_exc(), encoding="utf-8")


def summarize_ads(worker, asset_ids, run_id, folder, execution_notes):
    from .sponsors import WandBReasoner
    from .domain import digest
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    status = root / "summary-status.json"
    try:
        atomic_json(status, {"state":"RUNNING", "model":worker.settings.inference_model})
        contexts = []
        for identity in asset_ids:
            response = worker.client.get(f"/api/v2/workers/evidence-context/{str(UUID(identity))}", params={"run_id":run_id})
            response.raise_for_status()
            contexts.append(response.json())
        evidence = [row for context in contexts for row in context["evidence"]]
        execution = {"run":contexts[0]["run"], "operator_notebook_execution":execution_notes}
        result = WandBReasoner(worker.settings).summarize(evidence, execution)
        atomic_json(root / "summary-result.json", result)
        delivered = []
        for context in contexts:
            asset = context["asset"]
            metadata = {"input_asset_id":asset["id"], "input_sha256":asset["sha256"],
                "source_receipt":"summary-"+asset["id"]+"-"+result["input_digest"][:16],
                "source_kind":"generated_ad_evaluation", "title":"GLM — complete execution summary",
                "result":{"evaluator":"summary","status":"SUCCEEDED",
                    "provenance":{"model":worker.settings.inference_model,"version":"evidence-summary-v1","configuration_hash":digest({"contract":"evidence-summary-v1"})},
                    "observations":result,"limitations":["Generated explanation of recorded evidence; it does not add measurements or override policy gates."]}}
            response = worker.client.post("/api/v2/workers/evidence",data={"metadata":json.dumps(metadata)})
            response.raise_for_status()
            delivered.append(response.json()["id"])
        atomic_json(status,{"state":"SUCCEEDED","receipt_ids":delivered})
    except Exception as exc:
        atomic_json(status,{"state":"FAILED","error_type":type(exc).__name__,"detail":getattr(exc,"detail","Inspect the private summary error log")})
        (root / "summary-error.txt").write_text(traceback.format_exc(),encoding="utf-8")
