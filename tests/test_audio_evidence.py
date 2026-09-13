"""Contract tests; fixture transcripts are never runtime evidence."""
from types import SimpleNamespace
from pathlib import Path
import sys
from neuroloop_app.audio_evidence import AudioEvidence


def test_missing_stream_metadata_stays_unknown(tmp_path):
    (tmp_path / "model.bin").write_bytes(b"TEST_ONLY")
    adapter = AudioEvidence(tmp_path)
    asset = SimpleNamespace(kind="video", details={}, sha256="test")
    assert adapter.inspect(asset, lambda: None)["status"] == "UNAVAILABLE"
    asset.details = {"has_audio": False}
    assert adapter.inspect(asset, lambda: None)["status"] == "NOT_APPLICABLE"
    assert adapter.model is None


def test_transcript_retains_actual_segment_confidence_and_asset_identity(tmp_path, monkeypatch):
    (tmp_path / "model.bin").write_bytes(b"TEST_ONLY")
    observed = {}
    class Model:
        def __init__(self, path, **kwargs):
            observed.update(kwargs)
        def transcribe(self, path, **kwargs):
            observed.update(kwargs)
            return iter([SimpleNamespace(start=.2, end=1.2, text="TEST_ONLY", avg_logprob=-.4, no_speech_prob=.02)]), SimpleNamespace(language="en", language_probability=.8, duration=2, duration_after_vad=1)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    adapter = AudioEvidence(tmp_path)
    result = adapter.inspect(SimpleNamespace(kind="video", details={"has_audio": True}, sha256="actual-asset-id", path=Path("fixture.mp4")), lambda: None)
    assert result["asset_sha256"] == "actual-asset-id"
    assert result["weights_sha256"] == adapter.sha256
    assert result["segments"][0]["no_speech_prob"] == .02
    assert observed["local_files_only"] is True and observed["vad_filter"] is True
    assert result["limitations"]
