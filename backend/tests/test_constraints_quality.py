"""Synthetic acceptance tests for locked creative and media quality gates."""
from __future__ import annotations

import struct
import zlib

import pytest
from PIL import Image

from neuroloop.constraints import CreativeConstraints
from neuroloop.media_quality import (
    PreEvaluationRejected,
    evaluate_after_gate,
    pre_evaluation_gate,
    preflight_media,
)


def image_file(path, size=(32, 24)):
    Image.new("RGB", size, (80, 90, 100)).save(path, format="PNG")
    return path


def png_header_only(path, width, height):
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += struct.pack(">I", len(header)) + b"IHDR" + header + struct.pack(">I", zlib.crc32(b"IHDR" + header) & 0xFFFFFFFF)
    payload += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    path.write_bytes(payload)
    return path


def fake_video_probe(duration=2, width=320, height=180, frames=4, audio=False):
    streams = [{"codec_type": "video", "width": width, "height": height, "nb_read_frames": frames, "avg_frame_rate": "2/1"}]
    if audio:
        streams.append({"codec_type": "audio", "duration": str(duration)})
    return {"format": {"format_name": "synthetic", "duration": str(duration)}, "streams": streams}


def test_locked_copy_rejection_happens_before_mocked_evaluator(tmp_path):
    source = image_file(tmp_path / "candidate.png")
    called = False

    def evaluator(_candidate):
        nonlocal called
        called = True
        return {"score": 1.0}

    with pytest.raises(PreEvaluationRejected) as error:
        evaluate_after_gate(source, evaluator, "image", constraints={"required_copy": ["Keep exact copy"]})
    assert called is False
    assert error.value.report.constraints is not None
    assert any("copy" in reason.lower() for reason in error.value.report.violations)
    assert "no OCR" in error.value.report.message or "OCR" in error.value.report.message


def test_editable_metadata_can_prove_copy_claim_product_logo_and_declared_objects():
    baseline = {"product": "NeuroLoop", "layers": [{"id": "headline", "kind": "text", "text": "NeuroLoop"}, {"id": "claim", "kind": "claim", "text": "Measured model evidence"}, {"id": "logo", "kind": "logo", "asset_id": "logo-v1"}], "declared_objects": ["product-pack"]}
    candidate = {"product": "NeuroLoop", "layers": [{"id": "headline", "kind": "text", "text": "NeuroLoop"}, {"id": "claim", "kind": "claim", "text": "Measured model evidence"}, {"id": "logo", "kind": "logo", "asset_id": "logo-v1"}], "declared_objects": ["product-pack"]}
    report = CreativeConstraints(product="NeuroLoop", required_copy=["NeuroLoop"], claims=["Measured model evidence"], required_logo="logo-v1", preserve_logo=True, preserve_text=True, required_objects=["product-pack"]).check(candidate, baseline)
    assert report.passed, report.to_dict()
    assert report.evidence["verification_boundary"].startswith("declared metadata")


def test_duration_dimensions_aspect_and_audio_constraints_explain_failures():
    candidate = {"duration": 4.1, "width": 1280, "height": 720, "audio_streams": 0, "has_audio": False}
    report = CreativeConstraints(expected_duration=5, duration_tolerance=.1, expected_width=720, expected_height=1280, expected_aspect="portrait", require_audio=True, require_audio_signal=True).check(candidate)
    assert not report.passed
    names = {check["name"] for check in report.checks}
    assert {"duration", "dimensions", "aspect", "audio_streams", "audio_signal"} <= names
    assert "duration" in report.message and "audio" in report.message


def test_locked_properties_without_baseline_are_unverifiable_not_passed():
    report = CreativeConstraints(preserve_duration=True, preserve_dimensions=True, preserve_audio=True, preserve_text=True).check({"duration": 5, "width": 320, "height": 180, "has_audio": True, "audio_streams": 1})
    assert not report.passed
    assert any(check["status"] == "unverifiable" for check in report.checks)


def test_invalid_and_truncated_images_fail_closed(tmp_path):
    invalid = tmp_path / "invalid.png"
    invalid.write_bytes(b"not an image")
    truncated = tmp_path / "truncated.png"
    image_file(truncated)
    truncated.write_bytes(truncated.read_bytes()[:-12])
    for path in (invalid, truncated):
        report = preflight_media(path, "image")
        assert not report.passed
        assert report.violations
        assert "image_decode" in {check["name"] for check in report.checks}


def test_huge_dimensions_fail_without_decoding_pixels(tmp_path):
    path = png_header_only(tmp_path / "huge.png", 9000, 9000)
    report = preflight_media(path, "image")
    assert not report.passed
    assert any(check["code"] == "dimensions_out_of_bounds" for check in report.checks)


def test_zero_frame_and_malformed_container_are_rejected_without_models(monkeypatch, tmp_path):
    path = (tmp_path / "zero.mp4").write_bytes(b"synthetic")
    monkeypatch.setattr("neuroloop.media_quality._probe_ffprobe", lambda *_: ({"format": {"format_name": "synthetic", "duration": "1"}, "streams": [{"codec_type": "video", "width": 320, "height": 180, "nb_read_frames": 0}]}, None))
    monkeypatch.setattr("neuroloop.media_quality._decode", lambda *args, **kwargs: (True, b"", ""))
    zero = preflight_media(tmp_path / "zero.mp4", "video")
    assert not zero.passed
    assert any(check["code"] == "zero_or_excessive_frames" for check in zero.checks)

    monkeypatch.setattr("neuroloop.media_quality._probe_ffprobe", lambda *_: (None, "truncated container"))
    monkeypatch.setattr("neuroloop.media_quality._probe_ffmpeg", lambda *_: ({}, "truncated container"))
    malformed = preflight_media(tmp_path / "zero.mp4", "video")
    assert not malformed.passed
    assert any(check["code"] == "invalid_container" for check in malformed.checks)


def test_missing_and_silent_required_audio_are_rejected(monkeypatch, tmp_path):
    path = tmp_path / "synthetic.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr("neuroloop.media_quality._probe_ffprobe", lambda *_: (fake_video_probe(audio=False), None))
    monkeypatch.setattr("neuroloop.media_quality._decode", lambda *args, **kwargs: (True, b"frame", ""))
    missing = preflight_media(path, "video", require_audio=True)
    assert not missing.passed
    assert any(check["code"] == "missing_required_audio" for check in missing.checks)

    monkeypatch.setattr("neuroloop.media_quality._probe_ffprobe", lambda *_: (fake_video_probe(audio=True), None))
    monkeypatch.setattr("neuroloop.media_quality._audio_signal", lambda *_: (False, None))
    silent = preflight_media(path, "video", require_audio=True, require_audio_signal=True)
    assert not silent.passed
    assert any(check["code"] == "silent_or_undecodable_audio" for check in silent.checks)


def test_expected_duration_violation_is_a_quality_gate(monkeypatch, tmp_path):
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr("neuroloop.media_quality._probe_ffprobe", lambda *_: (fake_video_probe(duration=2), None))
    monkeypatch.setattr("neuroloop.media_quality._decode", lambda *args, **kwargs: (True, b"frame", ""))
    report = preflight_media(path, "video", expected_duration=5, duration_tolerance=.1)
    assert not report.passed
    assert any(check["code"] == "duration_mismatch" for check in report.checks)

