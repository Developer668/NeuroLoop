"""Contract tests use synthetic arrays only in the isolated temporary test database."""
import io
import json
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from neuroloop_app.api import create_app
from test_loop import settings, campaign

def test_import_checks_input_artifact_idempotency_and_frame(settings, tmp_path):
    app = create_app(settings)
    engine = app.state.engine
    c = campaign(engine)
    path = tmp_path / "test-only.png"
    Image.new("RGB", (32,32)).save(path)
    asset = engine.add_asset(c["id"], path, path.name)
    body = dict(input_asset_id=asset["id"], input_sha256=asset["sha256"], source_receipt="test-only-receipt",
        source_kind="reference_evaluation", title="Test only", result={"evaluator":"tribe", "status":"SUCCEEDED",
        "provenance":{"model":"TEST_ONLY", "version":"1", "configuration_hash":"test"},
        "limitations":["Synthetic contract test, never production evidence"]})
    buff = io.BytesIO()
    np.savez_compressed(buff, values=np.ones((2,20484)), times=np.array([0.,1.]))
    headers = {"Authorization":"Bearer " + "w"*40}
    with TestClient(app) as client:
        def post(data=body, payload=buff.getvalue()):
            return client.post("/api/v2/workers/evidence",headers=headers,data={"metadata":json.dumps(data)},files={"cortical":("x.npz",payload)})
        assert client.post("/api/v2/workers/evidence").status_code == 401
        assert post({**body,"input_sha256":"0"*64}).status_code == 422
        assert client.post("/api/v2/workers/evidence",headers=headers,data={"metadata":json.dumps(body)}).status_code == 422
        created = post()
        assert created.status_code == 201, created.text
        assert post().json()["id"] == created.json()["id"]
        assert post({**body,"title":"Changed"}).status_code == 409
        assert post(payload=b"not a cortical archive").status_code == 422
        operator = {"Authorization":"Bearer " + "o"*40}
        saved = client.get("/api/v2/evidence",headers=operator).json()
        assert len(saved)==1 and saved[0]["input_asset"]["sha256"]==asset["sha256"]
        frame=client.get(f"/api/evaluations/{created.json()['id']}/frame?index=1",headers=operator)
        assert frame.status_code==200 and frame.json()["time"]==1 and len(frame.json()["values"])==20484
        assert client.get(f"/api/evaluations/{created.json()['id']}/frame?index=2",headers=operator).status_code==422
        assert engine.campaign_detail(c["id"])["runs"]==[]
        regions=client.get(f"/api/evaluations/{created.json()['id']}/regions",headers=operator)
        assert regions.status_code==200
        assert all(abs(v-1)<1e-6 for row in regions.json()['regions'] for v in row['mean'])


def test_backup_failure_remains_retryable_and_never_claims_delivery(settings,tmp_path,monkeypatch):
    from neuroloop_app.artifact_backup import ArtifactExporter
    from neuroloop_app.db import ArtifactBackup
    settings.wandb_artifacts_enabled=True
    settings.wandb_project='test-only/project'
    from pydantic import SecretStr
    settings.wandb_api_key=SecretStr('not-a-real-key')
    app=create_app(settings);engine=app.state.engine;c=campaign(engine)
    path=tmp_path/'fixture.png';Image.new('RGB',(32,32)).save(path)
    asset=engine.add_asset(c['id'],path,path.name)
    exporter=ArtifactExporter(app.state.store,app.state.objects,engine)
    monkeypatch.setattr(exporter,'_upload',lambda *args: (_ for _ in ()).throw(ConnectionError('test-only')))
    exporter.drain()
    with app.state.store.transaction() as s:
        row=s.get(ArtifactBackup,'asset-'+asset['id'])
        assert row.status=='FAILED' and row.url is None
        row.next_attempt=0
    monkeypatch.setattr(exporter,'_upload',lambda *args:'https://example.test/verified-test-only')
    exporter.drain()
    with app.state.store.read() as s:
        row=s.get(ArtifactBackup,'asset-'+asset['id'])
        assert row.status=='VERIFIED' and row.error is None
