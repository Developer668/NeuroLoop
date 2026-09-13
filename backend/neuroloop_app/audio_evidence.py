"""Real, local speech evidence for multimodal review; never proof of silence."""
import hashlib
import time
from pathlib import Path


class AudioEvidence:
    def __init__(self, model_path):
        self.path = Path(model_path)
        weights = self.path / "model.bin"
        with weights.open("rb") as stream:
            self.sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        self.model = None

    def inspect(self, asset, check_cancelled):
        if asset.kind == "video" and "has_audio" not in asset.details:
            return {"status": "UNAVAILABLE", "asset_sha256": asset.sha256,
                    "reason": "Audio stream metadata is missing"}
        if asset.kind != "video" or asset.details["has_audio"] is False:
            return {"status": "NOT_APPLICABLE", "asset_sha256": asset.sha256,
                    "reason": "Verified media metadata has no audio stream"}
        from faster_whisper import WhisperModel
        check_cancelled()
        started = time.monotonic()
        if self.model is None:
            self.model = WhisperModel(str(self.path), device="cpu", compute_type="int8", local_files_only=True)
        segments, info = self.model.transcribe(str(asset.path), beam_size=5, vad_filter=True)
        rows = []
        for segment in segments:
            check_cancelled()
            rows.append({"start_seconds": segment.start, "end_seconds": segment.end,
                         "text": segment.text, "avg_logprob": segment.avg_logprob,
                         "no_speech_prob": segment.no_speech_prob})
        return {"status": "SUCCEEDED", "asset_sha256": asset.sha256,
                "model": "faster-whisper-small", "weights_sha256": self.sha256,
                "device": "cpu", "compute_type": "int8", "beam_size": 5, "vad_filter": True,
                "language": info.language, "language_probability": info.language_probability,
                "duration_seconds": info.duration, "speech_duration_seconds": info.duration_after_vad,
                "segments": rows, "elapsed_seconds": time.monotonic() - started,
                "limitations": ["ASR and voice detection can miss or misrecognize speech; no detected speech is not proof of silence.",
                                "Does not assess music licensing, sound quality, or nonverbal claims."]}
