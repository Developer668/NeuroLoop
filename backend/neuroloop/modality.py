"""Pure input-to-model routing for a single TRIBE evaluation.

The shipped TRIBE checkpoint was trained with text, audio, and video feature
keys.  A run may use a subset of those keys; the inactive extractors are not
prepared, so their model weights do not become resident for that evaluation.

This module intentionally contains no imports from torch, neuralset, or model
code.  It is used by the API for honest run planning and by the worker for the
actual model-loading decision.
"""
from __future__ import annotations

from dataclasses import dataclass


FEATURE_ORDER = ("text", "audio", "video")

_FEATURE_MODELS = {
    "text": {
        "role": "text_encoder",
        "name": "Llama-3.2-3B NF4/Q4",
        "asset": "models/text/llama-3.2-3b-unsloth-q4",
    },
    "audio": {
        "role": "audio_encoder",
        "name": "Wav2Vec-BERT 2.0",
        "asset": "models/audio/w2v-bert-2.0",
    },
    "video": {
        "role": "video_encoder",
        "name": "V-JEPA2 INT8",
        "asset": "tribev2-balanced-qv-local/quantized_video",
    },
}


@dataclass(frozen=True)
class ModalityPlan:
    """The model and preprocessing contract for one input asset."""

    input_kind: str
    tribe_features: tuple[str, ...]
    text_source: str
    input_adaptation: str | None
    notes: tuple[str, ...]

    def as_dict(self) -> dict:
        models = [
            {
                "role": "brain_readout",
                "name": "TRIBE v2 frozen checkpoint",
                "asset": "tribev2-balanced-qv-local/best.ckpt",
            }
        ]
        models.extend(dict(_FEATURE_MODELS[feature]) for feature in self.tribe_features)
        inactive = [feature for feature in FEATURE_ORDER if feature not in self.tribe_features]
        return {
            "input_kind": self.input_kind,
            "tribe_features": list(self.tribe_features),
            "models_loaded": models,
            "inactive_feature_encoders": inactive,
            "text_source": self.text_source,
            "input_adaptation": self.input_adaptation,
            "notes": list(self.notes),
            "reader_measurement": "not_available",
        }


def plan_for_input(
    kind: str,
    *,
    has_audio: bool = False,
    has_timed_text: bool = False,
    will_transcribe: bool = False,
    allow_static_presentation: bool = False,
) -> ModalityPlan:
    """Choose only the feature branches justified by the input contract.

    ``will_transcribe`` is used for an audio-bearing video/audio asset when
    local ASR will create word events before TRIBE is loaded.  It does not
    mean that a text encoder is used when the caller explicitly set
    ``no_speech``.
    """
    if kind not in {"image", "video", "audio", "text"}:
        raise ValueError(f"Unsupported input kind: {kind}")
    if kind == "image" and not allow_static_presentation:
        raise ValueError("Static-image TRIBE presentation requires explicit experimental-mode permission")
    if kind == "text" and not has_timed_text:
        raise ValueError("Text analysis requires a timed-word transcript")

    text_requested = has_timed_text or will_transcribe
    features: set[str] = set()
    adaptation: str | None = None
    notes: list[str] = []

    if kind == "image":
        # The current checkpoint has text/audio/video projectors, not a
        # compatible image projector.  Use the already documented experimental
        # image-to-video presentation and the trained video feature key.
        features.add("video")
        adaptation = "repeated_frame_video_presentation"
        notes.append(
            "Image is presented as a repeated-frame video because the shipped TRIBE checkpoint has no compatible direct image projector."
        )
        notes.append("DINOv2 is not loaded for this checkpoint; using it would require an image-compatible projector and validation.")
    elif kind == "video":
        features.add("video")
    elif kind == "audio":
        features.add("audio")
    else:
        features.add("text")
        notes.append("Timed text is a scheduled stimulus; it does not measure an individual reader's brain activity or feeling.")

    if kind != "text" and has_audio:
        features.add("audio")
    if text_requested:
        features.add("text")

    selected = tuple(feature for feature in FEATURE_ORDER if feature in features)
    if has_timed_text:
        text_source = "provided_timed_words"
    elif will_transcribe:
        text_source = "local_asr"
    else:
        text_source = "none"

    if "text" in selected and kind != "text":
        notes.append("Text features are included only from supplied timed words or local speech transcription; on-screen copy is not OCR'd.")
    if "audio" not in selected:
        notes.append("Audio encoder is not loaded for this run.")
    if "video" not in selected:
        notes.append("Video encoder is not loaded for this run.")
    if "text" not in selected:
        notes.append("Text encoder is not loaded for this run.")

    return ModalityPlan(
        input_kind=kind,
        tribe_features=selected,
        text_source=text_source,
        input_adaptation=adaptation,
        notes=tuple(notes),
    )


def plan_for_asset(kind: str, details: dict, config: dict) -> ModalityPlan:
    """Derive a plan from persisted asset metadata and a run request."""
    words = config.get("transcript") or details.get("transcript") or []
    has_audio = bool(details.get("has_audio"))
    will_transcribe = bool(has_audio and not config.get("no_speech") and not words)
    return plan_for_input(
        kind,
        has_audio=has_audio,
        has_timed_text=bool(words),
        will_transcribe=will_transcribe,
        allow_static_presentation=bool(config.get("allow_static_presentation")),
    )


def routing_capabilities() -> dict:
    """Return an API-safe description of the routing policy."""
    return {
        "video": {
            "features": ["video"],
            "adds": {"audio": "when an audio stream is present", "text": "when timed words or local ASR are available"},
        },
        "image": {
            "features": ["video"],
            "adaptation": "explicit repeated-frame presentation",
            "direct_image_encoder": "not_selected_for_current_checkpoint",
        },
        "audio": {
            "features": ["audio"],
            "adds": {"text": "when timed words or local ASR are available"},
        },
        "text": {
            "features": ["text"],
            "requires": "timed words",
            "reader_measurement": "not_available",
        },
        "always": ["TRIBE v2 frozen brain readout"],
    }
