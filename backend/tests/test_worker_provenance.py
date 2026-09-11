from types import SimpleNamespace

import hashlib
import json
import os

import numpy as np
import pytest

from neuroloop.config import settings
from neuroloop.db import Asset, Run, Session, initialize
from neuroloop import inference
from neuroloop.persistence import (
    ArtifactIntegrityError,
    atomic_json,
    atomic_numpy,
    publish_artifact_manifest,
    validate_artifact_manifest,
)
from neuroloop.readout import summarize
from neuroloop import worker


def test_profile_id_tracks_optional_and_resident_model_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(inference, "settings", lambda: SimpleNamespace(root=tmp_path))
    tsam_weights = tmp_path / "models/emotion/tsam/weights/tsam_weights.tar"
    resident_weights = tmp_path / "models/text/llama-3.2-3b-unsloth-q4/model.safetensors"
    tsam_weights.parent.mkdir(parents=True)
    resident_weights.parent.mkdir(parents=True)
    tsam_weights.write_bytes(b"tsam-v1")
    resident_weights.write_bytes(b"resident-v1")

    first = inference.profile_id()
    tsam_weights.write_bytes(b"tsam-v2")
    second = inference.profile_id()
    resident_weights.write_bytes(b"resident-v2")
    third = inference.profile_id()

    assert first != second
    assert second != third


def test_profile_snapshot_reuses_unchanged_large_files(monkeypatch, tmp_path):
    monkeypatch.setattr(inference, "settings", lambda: SimpleNamespace(root=tmp_path))
    resident_weights = tmp_path / "models/vision/dinov2-large/model.safetensors"
    resident_weights.parent.mkdir(parents=True)
    resident_weights.write_bytes(b"a" * (2 * 1024 * 1024))

    digests = []
    original_digest = inference._digest
    monkeypatch.setattr(
        inference,
        "_digest",
        lambda path: digests.append(path) or original_digest(path),
    )

    first = inference.profile_snapshot()
    first_id = inference.profile_id(first)
    second = inference.profile_snapshot()
    assert second == first
    second['manifest']['files']['models/vision/dinov2-large']['models/vision/dinov2-large/model.safetensors'] = 'caller-mutation'
    assert inference.profile_snapshot() == first
    assert len(digests) == 1

    replacement = resident_weights.with_name("replacement.safetensors")
    replacement.write_bytes(b"b" * (2 * 1024 * 1024))
    os.replace(replacement, resident_weights)

    third = inference.profile_snapshot()
    assert len(digests) == 2
    assert inference.profile_id(third) != first_id


def test_published_artifacts_are_hash_linked_and_immutable(tmp_path):
    for name, value in {
        "prediction.npy": b"prediction",
        "segments.json": b"[]",
        "evidence.json": b'{"profile":"profile-v1"}',
    }.items():
        (tmp_path / name).write_bytes(value)

    manifest = publish_artifact_manifest(
        tmp_path, cache_key="cache-v1", profile="profile-v1", asset_sha256="asset-v1"
    )
    assert validate_artifact_manifest(
        tmp_path, cache_key="cache-v1", profile="profile-v1", asset_sha256="asset-v1"
    ) == manifest

    (tmp_path / "prediction.npy").write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="changed"):
        validate_artifact_manifest(
            tmp_path, cache_key="cache-v1", profile="profile-v1", asset_sha256="asset-v1"
        )
    with pytest.raises(ArtifactIntegrityError, match="immutable"):
        publish_artifact_manifest(
            tmp_path, cache_key="cache-v1", profile="profile-v1", asset_sha256="asset-v1"
        )


def test_worker_rejects_a_tampered_cached_prediction(tmp_path, monkeypatch):
    initialize()
    source = settings().data / "assets" / "provenance-fixture.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"fixture")
    asset_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    asset = Asset(
        id="provenance-asset",
        name="provenance-fixture.mp4",
        kind="video",
        sha256=asset_sha256,
        path=str(source),
        size=source.stat().st_size,
        details={"duration": 1.0, "has_audio": False},
    )
    run = Run(
        id="provenance-run",
        project_id="provenance-project",
        status="running",
        config={"request": {"max_seconds": 60}},
        max_evaluations=1,
    )
    with Session.begin() as db:
        db.add_all([asset, run])

    config = {"no_speech": True}
    profile = inference.profile_id()
    meaningful = {
        key: config.get(key)
        for key in [
            "no_speech",
            "transcript",
            "allow_static_presentation",
            "presentation_seconds",
            "include_tsam",
            "include_kragel",
        ]
    }
    meaningful["transcript"] = []
    meaningful["metric_schema"] = worker.METRIC
    cache_key = hashlib.sha256(
        json.dumps(
            {"asset": asset_sha256, "profile": profile, "preprocessing": meaningful},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    output = settings().data / "results" / cache_key
    prediction = np.random.default_rng(42).normal(size=(1, 20484)).astype(np.float32)
    atomic_numpy(output / "prediction.npy", prediction)
    atomic_json(output / "segments.json", [{"start": 0.0, "duration": 1.0}])
    atomic_json(
        output / "evidence.json",
        {
            **summarize(prediction, [0.0]),
            "profile": profile,
            "segment_durations": [1.0],
            "source_duration": 1.0,
            "seconds": 0.0,
        },
    )
    publish_artifact_manifest(
        output,
        cache_key=cache_key,
        profile=profile,
        asset_sha256=asset_sha256,
        profile_manifest=inference.profile_manifest(),
    )
    first = worker.evaluation(run.id, asset, config)
    assert first.cache_key == cache_key

    (output / "prediction.npy").write_bytes(b"tampered")
    monkeypatch.setattr(worker.inference, "evaluate", lambda *args, **kwargs: pytest.fail("cache must not execute"))
    with pytest.raises(ArtifactIntegrityError, match="changed"):
        worker.evaluation(run.id, asset, config)
