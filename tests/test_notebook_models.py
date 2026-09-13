"""CPU contract tests. Fixture media/model answers never enter application code."""
from pathlib import Path
from types import SimpleNamespace
import json

import httpx
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from neuroloop_app.api import create_app
from neuroloop_app.config import Settings
from neuroloop_app.domain import CampaignSpec, BrandSpec, RunConfig, StartRun, ModelProvenance, PlanResult, DecisionResult, EvaluationResult
from neuroloop_app.model_adapters import H3Adapter, IdeogramAdapter, configure_models, dimensions
from neuroloop_app.notebook import ModelRegistry, NotebookWorker, GenerationContext, EvaluationContext, LocalAsset, GeneratedFile, EvaluationOutput
from neuroloop_app.sponsors import ProviderFailure
from neuroloop_app.vision_adapter import VisionAdapter

P = ModelProvenance(model="TEST_ONLY", version="fixture", configuration_hash="test")


def settings(tmp_path, **kwargs):
    return Settings(_env_file=None, data_dir=tmp_path / "db", operator_token="o" * 40,
        worker_token="w" * 40, signing_key="s" * 40, WANDB_API_KEY="TEST_ONLY", TYPESAFE_API_KEY="TEST_ONLY",
        inference_model="TEST_ONLY", **kwargs)


def test_lazy_fp8_registration_and_missing_research(tmp_path):
    registry = configure_models(ModelRegistry(), settings(tmp_path, enable_h3=True, enable_ideogram=True,
        enable_legacy_evaluators=True, research_root=tmp_path))
    assert all(entry.callable is None for entry in registry.models.values())
    assert registry.describe()["generate_image"]["supports_regeneration"] is False
    assert registry.describe()["generate_image"]["supports_media_references"] is False
    assert registry.describe()["evaluate_tribe"]["status"] == "NOT_CONFIGURED"
    assert dimensions("9:16", 1024) == (576, 1024)


def test_h3_preserves_all_reference_paths_seed_and_output_scope(tmp_path):
    s = settings(tmp_path)
    adapter = H3Adapter(s)
    seen = {}
    def generate(prompt, **kwargs):
        seen.update(kwargs)
        return tmp_path / "actual.mp4", {"duration": 15}
    adapter.runtime = SimpleNamespace(generate=generate)
    parent = LocalAsset("p", tmp_path / "p.mp4", "video", "video/mp4", "a"*64, {})
    image = LocalAsset("i", tmp_path / "i.png", "image", "image/png", "b"*64, {})
    ctx = GenerationContext("j", "c", {"duration_seconds": 15, "aspect_ratio": "16:9"}, "test", {}, {"seed": 73}, [image], parent, tmp_path, lambda: False, 120)
    result = adapter(ctx)
    assert seen["reference_paths"] == [parent.path, image.path]
    assert seen["seed"] == 73 and seen["output_dir"] == tmp_path and seen["frames"] == 345
    assert result.path == tmp_path / "actual.mp4"


def test_ideogram_rejects_media_before_loading_weights(tmp_path):
    adapter = IdeogramAdapter(settings(tmp_path))
    image = LocalAsset("i", tmp_path / "i.png", "image", "image/png", "b"*64, {})
    ctx = GenerationContext("j", "c", {}, "test", {}, {}, [image], None, tmp_path, lambda: False, 120)
    with pytest.raises(ProviderFailure, match="cannot consume media"):
        adapter(ctx)
    assert adapter.pipe is None


def test_ideogram_rejects_prose_before_loading_weights(tmp_path):
    adapter = IdeogramAdapter(settings(tmp_path))
    ctx = GenerationContext("j", "c", {}, "A prose brief is not a structured caption", {}, {}, [], None, tmp_path, lambda: False, 120)
    with pytest.raises(ProviderFailure, match="structured JSON caption"):
        adapter(ctx)
    assert adapter.pipe is None


def test_ideogram_caption_preserves_reviewed_text_and_layout():
    from neuroloop_app.ideogram_caption import caption_json
    caption = {"high_level_description": "An editorial advertisement.",
               "compositional_deconstruction": {"background": "Cream paper", "elements": [
                   {"type": "text", "bbox": [100, 100, 300, 900], "text": "Créate", "desc": "Teal headline"}]}}
    encoded = caption_json(json.dumps(caption))
    assert json.loads(encoded) == caption
    assert "Créate" in encoded
    assert list(json.loads(encoded)["compositional_deconstruction"]["elements"][0]) == ['type', 'bbox', 'text', 'desc']


def test_vision_sends_real_image_bytes_and_validates_result(tmp_path):
    path = tmp_path / "fixture.png"
    Image.new("RGB", (64,64), "blue").save(path)
    asset = LocalAsset("i", path, "image", "image/png", "b"*64, {})
    def handler(request):
        body = json.loads(request.content)
        parts = body["messages"][1]["content"]
        assert parts[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"status": "SUCCEEDED", "scores": {"creative_quality": {"value": .5, "source": "TEST_ONLY", "meaning": "Test fixture"}}})}}]})
    adapter = VisionAdapter(settings(tmp_path, vision_model="TEST_ONLY"), httpx.Client(transport=httpx.MockTransport(handler)))
    result = adapter(EvaluationContext("j", "c", {}, asset, [], [], tmp_path, lambda: False))
    assert result.result.provenance == adapter.provenance
    assert result.result.limitations


def test_vision_rejects_invented_image_timestamp(tmp_path):
    path = tmp_path / 'fixture.png'
    Image.new('RGB', (64, 64), 'blue').save(path)
    asset = LocalAsset('i', path, 'image', 'image/png', 'b'*64, {})
    body = {'status': 'SUCCEEDED', 'scores': {'creative_quality': {'value': .5, 'source': 'TEST_ONLY', 'meaning': 'Fixture'}},
            'observations': {'frame_evidence': [{'timestamp_seconds': 3.2, 'description': 'Invented video timestamp'}]}}
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        'choices': [{'message': {'content': json.dumps(body)}}]})))
    adapter = VisionAdapter(settings(tmp_path, vision_model='TEST_ONLY'), client)
    with pytest.raises(ProviderFailure, match='evidence schema'):
        adapter(EvaluationContext('j', 'c', {}, asset, [], [], tmp_path, lambda: False))


def test_video_frame_index_maps_to_supplied_time_and_rejects_wrong_index(tmp_path):
    asset = LocalAsset('test-only', tmp_path/'fixture.mp4', 'video', 'video/mp4', 'a'*64, {'duration_seconds':5.175})
    evidence = {'frame_index':2,'description':'Test fixture description'}
    body = {'status':'SUCCEEDED','scores':{'creative_quality':{'value':.5,'source':'TEST_ONLY','meaning':'Test fixture'}},'observations':{'frame_evidence':[evidence]}}
    client = httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(body)}}]})))
    adapter = VisionAdapter(settings(tmp_path,vision_model='TEST_ONLY'),client)
    adapter.media_content = lambda *args, **kwargs: [{'type':'text','text':'TEST_ONLY sampled frames'}]
    ctx = EvaluationContext('test','test',{},asset,[],[],tmp_path,lambda:False)
    result=adapter(ctx).result
    assert result.observations['frame_evidence'][0]['timestamp_seconds']==5.175*2.5/6
    body['constraints'] = [{'name':'test','status':'UNKNOWN','evidence':'TEST_ONLY','description':''}]
    assert adapter(ctx).result.constraints[0].status == 'UNKNOWN'
    body['constraints'][0]['description'] = 'Substantive extra assertion'
    with pytest.raises(ProviderFailure): adapter(ctx)
    body.pop('constraints')
    evidence['frame_index']=6
    with pytest.raises(ProviderFailure): adapter(ctx)
    evidence.update(frame_index=2,timestamp_seconds=0)
    with pytest.raises(ProviderFailure): adapter(ctx)


def test_worker_full_two_round_loop_with_text_alternatives(tmp_path):
    s = settings(tmp_path)
    app = create_app(s)
    registry = ModelRegistry()
    generated_contexts = []
    def generate(ctx):
        generated_contexts.append(ctx)
        path = ctx.output_dir / "TEST_ONLY.png"
        Image.new("RGB", (64,64), "blue").save(path)
        return GeneratedFile(path, {"seed": ctx.parameters["seed"], "conditioning": ctx.conditioning})
    def evaluate(ctx):
        return EvaluationOutput(EvaluationResult(evaluator="vision", status="SUCCEEDED", provenance=P,
            scores={"creative_quality": {"value": .5, "source": "TEST_ONLY", "meaning": "Test fixture"}},
            constraints=[{"name": n, "status": "PASS", "evidence": "TEST_ONLY"} for n in ctx.required_constraints]))
    registry.register_generator("image", provenance=P, loader=lambda: generate, supports_regeneration=False)
    registry.register_evaluator("vision", provenance=P, loader=lambda: evaluate)
    def plan(payload, media_content=None):
        candidates = []
        for slot in payload["candidate_slots"]:
            parent = next((p for p in payload["parents"] if p["creative"]["id"] == slot["parent_creative_id"]), None)
            candidates.append({**slot, "prompt": "TEST_ONLY image", "seed": 73, "strategy": "TEST_ONLY",
                "edit_intent": {"primary_goal": "Test", "preserve": ["product_identity"],
                "optimization": __import__("test_loop").optimization_for(parent["evidence"]["evaluations"]) if parent else None,
                "reasoning_evidence_ids": [e["id"] for e in parent["evidence"]["evaluations"]] if parent else []}})
        return PlanResult(summary="TEST_ONLY", candidates=candidates, model="TEST_ONLY")
    def decide(payload):
        assert "REGENERATE" not in payload["allowed_actions"]
        return DecisionResult(decision="GENERATE_ALTERNATIVE", selected_creative_ids=payload["allowed_creative_ids"][:1],
            confidence=.9, reason_codes=["TEST_ONLY"], model="TEST_ONLY", raw_response={"test_only": True})
    with TestClient(app, headers={"Authorization": "Bearer " + "w"*40}) as client:
        engine = app.state.engine
        c = engine.create_campaign(CampaignSpec(title="TEST_ONLY", brief="Test fixture", brand=BrandSpec(name="Test"), media_kind="image", aspect_ratio="1:1"))
        run = engine.start(c["id"], StartRun(config=RunConfig(initial_candidates=1, beam_width=1, branch_factor=1, max_rounds=2, optional_evaluators=[])), "fixture")
        worker = NotebookWorker(registry, s, client=client, cache_dir=tmp_path / "cache")
        def summarize(evidence, execution):
            from neuroloop_app.domain import digest
            return {"summary": "TEST_ONLY", "findings": [], "limitations": [], "next_steps": [],
                    "evidence_ids": [e["id"] for e in evidence], "provider_receipt": {"model": "TEST_ONLY"},
                    "input_digest": digest({"evidence": evidence, "execution": execution})}
        worker.reasoner = SimpleNamespace(plan=plan, summarize=summarize)
        worker.kernel = SimpleNamespace(decide=decide, review_plan=lambda payload: __import__("neuroloop_app.domain", fromlist=["PlanReview"]).PlanReview.model_validate(__import__("test_loop").review_for(payload)))
        for _ in range(12):
            if engine.snapshot(run["id"])["run"]["state"] == "READY_FOR_REVIEW": break
            assert worker.run_once()
        assert worker.run_once()  # Automatic summary is explanatory; the decision remains paused for human review.
        snapshot = engine.snapshot(run["id"])
        assert snapshot["run"]["state"] == "READY_FOR_REVIEW"
        assert len(snapshot["creatives"]) == 2
        assert generated_contexts[1].current_media is not None
        assert generated_contexts[1].conditioning == "text_alternative"
        assert generated_contexts[1].parameters["seed"] == 73
        assert snapshot["creatives"][1]["creation_type"] == "text_alternative"
        assert all(j["status"] == "SUCCEEDED" for j in snapshot["jobs"])
        assert worker.reconcile() == 0  # Delivered receipts do not regenerate media.


def test_idle_worker_releases_memory(tmp_path):
    parked = []
    registry = ModelRegistry()
    registry.register_generator("image", provenance=P, loader=lambda: lambda ctx: None, park=lambda: parked.append(True))
    registry.models["generate_image"].callable = lambda ctx: None
    worker = NotebookWorker(registry, settings(tmp_path).model_copy(update={"worker_idle_seconds": 0}), cache_dir=tmp_path / "cache")
    worker.run_once = lambda: False
    worker.start()
    worker.thread.join(timeout=3)
    assert not worker.thread.is_alive()
    assert worker.last_status["state"] == "IDLE_STOPPED"
    assert parked == [True]


def test_corrupt_image_returns_validation_error(tmp_path):
    import base64
    from neuroloop_app.storage import inspect_media, StorageError
    path = tmp_path / "corrupt.png"
    path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1cAAAAASUVORK5CYII="))
    with pytest.raises(StorageError, match="damaged"):
        inspect_media(path, settings(tmp_path))
