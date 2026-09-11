"""Cheap, fail-closed media quality gates used before evaluation.

The inspector decodes metadata and media with local Pillow/FFmpeg tools only.
It never calls a model and returns evidence for every rejection so corrupt or
unsafe candidates cannot be rescued by a downstream score.
"""
from __future__ import annotations

from array import array
from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import warnings
from typing import Any, Callable

from PIL import Image, ImageFile

from .config import settings


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_KINDS = {"video", "audio"}
DEFAULT_MAX_WIDTH = 8192
DEFAULT_MAX_HEIGHT = 8192
DEFAULT_MAX_PIXELS = 40_000_000
DEFAULT_MAX_FRAMES = 100_000


class MediaQualityError(ValueError):
    """A media file or candidate failed a pre-evaluation quality gate."""

    def __init__(self, report: "MediaQualityReport | PreEvaluationReport") -> None:
        self.report = report
        super().__init__(report.message)


@dataclass(frozen=True)
class MediaQualityLimits:
    max_file_size: int | None = None
    max_width: int = DEFAULT_MAX_WIDTH
    max_height: int = DEFAULT_MAX_HEIGHT
    max_pixels: int = DEFAULT_MAX_PIXELS
    max_duration: float | None = None
    max_frames: int = DEFAULT_MAX_FRAMES
    timeout_seconds: int = 30

    @classmethod
    def current(cls) -> "MediaQualityLimits":
        s = settings()
        return cls(max_file_size=int(s.max_upload_bytes), max_duration=float(s.max_media_seconds))


@dataclass(frozen=True)
class MediaExpectation:
    duration: float | None = None
    duration_tolerance: float = 0.2
    width: int | None = None
    height: int | None = None
    aspect: str | float | None = None
    aspect_tolerance: float = 0.01
    require_audio: bool = False
    require_audio_signal: bool = False
    required_audio_streams: int | None = None


@dataclass(frozen=True)
class MediaQualityReport:
    passed: bool
    kind: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    checks: tuple[dict[str, Any], ...] = ()
    violations: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        return "passed" if self.passed else "rejected"

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.violations

    @property
    def evidence(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "metadata": dict(self.metadata), "checks": list(self.checks), "violations": list(self.violations), "verification": "local container/image decode; no model invocation"}

    @property
    def message(self) -> str:
        return "Media quality checks passed." if self.passed else "Media quality gate rejected the file: " + "; ".join(self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "status": self.status, "kind": self.kind, "path": self.path, "metadata": dict(self.metadata), "checks": list(self.checks), "violations": list(self.violations), "reasons": list(self.violations), "evidence": self.evidence, "message": self.message}

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


@dataclass(frozen=True)
class PreEvaluationReport:
    passed: bool
    quality: MediaQualityReport
    constraints: Any = None

    @property
    def violations(self) -> tuple[str, ...]:
        values = list(self.quality.violations)
        if self.constraints is not None:
            values.extend(self.constraints.violations)
        return tuple(values)

    @property
    def message(self) -> str:
        return "Pre-evaluation gates passed." if self.passed else "Pre-evaluation gate rejected the candidate: " + "; ".join(self.violations)

    @property
    def evidence(self) -> dict[str, Any]:
        return {"quality": self.quality.to_dict(), "constraints": self.constraints.to_dict() if self.constraints is not None else None, "order": "quality and locked constraints are checked before evaluator"}

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "status": "passed" if self.passed else "rejected", "violations": list(self.violations), "evidence": self.evidence, "message": self.message}


class PreEvaluationRejected(MediaQualityError):
    """Raised by ``evaluate_after_gate`` before an evaluator is called."""


def _binary(name: str) -> str | None:
    configured = os.getenv("NEUROLOOP_" + name.upper())
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            return None
    return None


def _add(checks: list[dict[str, Any]], violations: list[str], name: str, passed: bool, code: str, message: str, expected: Any = None, actual: Any = None, *, verification: str = "local_media_decode", status: str | None = None) -> None:
    checks.append({"name": name, "passed": passed, "status": status or ("passed" if passed else "failed"), "code": code, "expected": expected, "actual": actual, "message": message, "verification": verification})
    if not passed:
        violations.append(message)


def _kind(path: Path, kind: str | None) -> str:
    if kind is not None:
        return kind
    return "image" if path.suffix.lower() in IMAGE_SUFFIXES else "video"


def _limits(value: MediaQualityLimits | Mapping[str, Any] | None) -> MediaQualityLimits:
    current = MediaQualityLimits.current()
    if value is None:
        return current
    if isinstance(value, MediaQualityLimits):
        return value
    if not isinstance(value, Mapping):
        raise MediaQualityError(MediaQualityReport(False, "unknown", "", violations=("Media limits must be a mapping or MediaQualityLimits.",)))
    fields = {key: item for key, item in value.items() if key in MediaQualityLimits.__dataclass_fields__}
    return MediaQualityLimits(**{**current.__dict__, **fields})


def _expectation(value: MediaExpectation | Mapping[str, Any] | None, **overrides: Any) -> MediaExpectation:
    data: dict[str, Any] = {}
    if isinstance(value, MediaExpectation):
        data.update(value.__dict__)
    elif value is not None:
        if not isinstance(value, Mapping):
            raise ValueError("Media expectation must be a mapping or MediaExpectation")
        data.update(value)
    aliases = {"expected_duration": "duration", "expected_width": "width", "expected_height": "height", "expected_aspect": "aspect", "audio_streams": "required_audio_streams"}
    for key, item in list(data.items()):
        if key in aliases:
            data[aliases[key]] = data.pop(key)
    for key, item in overrides.items():
        if item is not None:
            data[aliases.get(key, key)] = item
    return MediaExpectation(**{key: item for key, item in data.items() if key in MediaExpectation.__dataclass_fields__})


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 and result == float(value) else None


def _probe_ffprobe(path: Path, timeout: int) -> tuple[dict[str, Any] | None, str | None]:
    binary = _binary("ffprobe")
    if not binary:
        return None, "ffprobe is unavailable"
    command = [binary, "-v", "error", "-protocol_whitelist", "file,pipe", "-count_frames", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"ffprobe failed: {type(exc).__name__}"
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
        return None, "container probe failed" + (f": {detail}" if detail else "")
    try:
        data = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "container probe returned malformed metadata"
    return data if isinstance(data, dict) else None, None


def _probe_ffmpeg(path: Path, timeout: int) -> tuple[dict[str, Any], str | None]:
    binary = _binary("ffmpeg")
    if not binary:
        return {}, "No local FFmpeg decoder is available"
    command = [binary, "-hide_banner", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(path), "-f", "null", "-"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"FFmpeg probe failed: {type(exc).__name__}"
    text = result.stderr.decode("utf-8", errors="replace")
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = float(duration_match.group(1)) * 3600 + float(duration_match.group(2)) * 60 + float(duration_match.group(3)) if duration_match else None
    video_match = re.search(r"Video:.*?(\d{1,6})x(\d{1,6})", text, flags=re.DOTALL)
    audio = bool(re.search(r"Stream #\S+.*?Audio:", text))
    frame_match = re.findall(r"frame=\s*(\d+)", text)
    return {"format": {"format_name": "ffmpeg-probed"}, "streams": ([{"codec_type": "video", "width": int(video_match.group(1)), "height": int(video_match.group(2)), "nb_read_frames": int(frame_match[-1]) if frame_match else None}] if video_match else []) + ([{"codec_type": "audio"}] if audio else []), "duration": duration, "_decode_returncode": result.returncode}, ("container decode failed" if result.returncode else None)


def _stream_info(data: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    streams = data.get("streams")
    streams = [item for item in streams if isinstance(item, Mapping)] if isinstance(streams, list) else []
    fmt = data.get("format") if isinstance(data.get("format"), Mapping) else {}
    return dict(fmt), [dict(item) for item in streams]


def _decode(path: Path, selector: str, timeout: int, *, first_frame: bool = False) -> tuple[bool, bytes, str]:
    binary = _binary("ffmpeg")
    if not binary:
        return False, b"", "No local FFmpeg decoder is available"
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(path), "-map", selector]
    if first_frame:
        command += ["-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
    else:
        command += ["-f", "null", "-"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, b"", f"decoder failed: {type(exc).__name__}"
    detail = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
    return result.returncode == 0, result.stdout, detail


def _audio_signal(path: Path, timeout: int) -> tuple[bool | None, str | None]:
    binary = _binary("ffmpeg")
    if not binary:
        return None, "No local FFmpeg decoder is available"
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(path), "-map", "0:a:0", "-vn", "-t", "5", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"audio decode failed: {type(exc).__name__}"
    if result.returncode or not result.stdout:
        return None, result.stderr.decode("utf-8", errors="replace").strip()[-500:] or "audio stream could not be decoded"
    samples = array("h")
    samples.frombytes(result.stdout[: 2 * 8000 * 5])
    return any(sample != 0 for sample in samples), None


def _image(path: Path, limits: MediaQualityLimits, checks: list[dict[str, Any]], violations: list[str], metadata: dict[str, Any]) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            ImageFile.LOAD_TRUNCATED_IMAGES = False
            with Image.open(path) as image:
                width, height = image.width, image.height
                frames = _int(getattr(image, "n_frames", 1)) or 0
                metadata.update({"format": image.format, "width": width, "height": height, "frame_count": frames, "duration": None, "has_audio": False, "audio_streams": 0})
                dimensions_ok = width > 0 and height > 0 and width <= limits.max_width and height <= limits.max_height and width * height <= limits.max_pixels
                _add(checks, violations, "dimensions_sane", dimensions_ok, "dimensions_out_of_bounds", "Image dimensions are zero or exceed the configured bounds.", {"max_width": limits.max_width, "max_height": limits.max_height, "max_pixels": limits.max_pixels}, {"width": width, "height": height})
                _add(checks, violations, "frame_count", frames > 0 and frames <= limits.max_frames, "zero_or_excessive_frames", "Image has no decodable frames or exceeds the frame bound.", {"min": 1, "max": limits.max_frames}, frames)
                if not dimensions_ok:
                    return
                image.verify()
            with Image.open(path) as image:
                durations: list[float] = []
                for index in range(frames):
                    image.seek(index)
                    image.load()
                    duration = _float(image.info.get("duration"))
                    if duration is not None and duration >= 0:
                        durations.append(duration / 1000)
                if len(durations) == frames and frames > 1:
                    metadata["duration"] = sum(durations)
        _add(checks, violations, "image_decode", True, "image_decoded", "Image opened and all declared frames decoded.")
    except Exception as exc:
        metadata["decode_error"] = type(exc).__name__
        _add(checks, violations, "image_decode", False, "invalid_or_truncated_image", "Image is invalid, truncated, or could not be decoded: " + type(exc).__name__, verification="local_image_decode")


def _aspect_matches(actual: float | None, expected: str | float, tolerance: float) -> bool:
    if actual is None:
        return False
    if isinstance(expected, str) and expected.lower() in {"landscape", "portrait", "square"}:
        name = expected.lower()
        return (name == "landscape" and actual > 1) or (name == "portrait" and actual < 1) or (name == "square" and abs(actual - 1) <= tolerance)
    try:
        numeric = float(expected.split(":")[0]) / float(expected.split(":")[1]) if isinstance(expected, str) and ":" in expected else float(expected)
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    return math.isfinite(numeric) and numeric > 0 and abs(actual - numeric) <= tolerance


def preflight_media(path: str | Path, kind: str | None = None, *, expected: MediaExpectation | Mapping[str, Any] | None = None, expected_duration: float | None = None, duration_tolerance: float | None = None, expected_width: int | None = None, expected_height: int | None = None, expected_aspect: str | float | None = None, aspect_tolerance: float | None = None, require_audio: bool | None = None, require_audio_signal: bool | None = None, required_audio_streams: int | None = None, limits: MediaQualityLimits | Mapping[str, Any] | None = None) -> MediaQualityReport:
    """Inspect a local image/video/audio file before any evaluator is called."""
    file_path = Path(path)
    media_kind = _kind(file_path, kind)
    checks: list[dict[str, Any]] = []
    violations: list[str] = []
    metadata: dict[str, Any] = {}
    try:
        bound = _limits(limits)
    except MediaQualityError as exc:
        return exc.report if isinstance(exc.report, MediaQualityReport) else MediaQualityReport(False, media_kind, str(file_path), violations=(str(exc),))
    expectation = _expectation(expected, expected_duration=expected_duration, duration_tolerance=duration_tolerance, expected_width=expected_width, expected_height=expected_height, expected_aspect=expected_aspect, aspect_tolerance=aspect_tolerance, require_audio=require_audio, require_audio_signal=require_audio_signal, required_audio_streams=required_audio_streams)
    display_path = file_path.name
    if media_kind not in {"image", "video", "audio"}:
        _add(checks, violations, "kind", False, "unsupported_kind", f"Unsupported media kind {media_kind!r}.", {"image", "video", "audio"}, media_kind)
        return MediaQualityReport(False, media_kind, display_path, metadata, tuple(checks), tuple(violations))
    if "://" in str(path):
        _add(checks, violations, "local_path", False, "remote_source", "Only an existing local media file may be inspected.")
        return MediaQualityReport(False, media_kind, display_path, metadata, tuple(checks), tuple(violations))
    if not file_path.is_file():
        _add(checks, violations, "file_exists", False, "missing_file", "Media file does not exist or is not a regular file.", verification="local_filesystem")
        return MediaQualityReport(False, media_kind, display_path, metadata, tuple(checks), tuple(violations))
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        _add(checks, violations, "file_stat", False, "file_stat_failed", "Media file metadata could not be read: " + type(exc).__name__, verification="local_filesystem")
        return MediaQualityReport(False, media_kind, display_path, metadata, tuple(checks), tuple(violations))
    metadata["file_size"] = size
    _add(checks, violations, "file_size", size > 0 and (bound.max_file_size is None or size <= bound.max_file_size), "file_size_out_of_bounds", "Media file is empty or exceeds the configured file-size bound.", {"min": 1, "max": bound.max_file_size}, size, verification="local_filesystem")
    if violations:
        return MediaQualityReport(False, media_kind, display_path, metadata, tuple(checks), tuple(violations))

    if media_kind == "image":
        _image(file_path, bound, checks, violations, metadata)
    else:
        probed, probe_error = _probe_ffprobe(file_path, bound.timeout_seconds)
        if probed is None:
            probed, fallback_error = _probe_ffmpeg(file_path, bound.timeout_seconds)
            probe_error = fallback_error if not probed else None
        fmt, streams = _stream_info(probed)
        metadata["format"] = fmt.get("format_name") or fmt.get("format_long_name")
        video_streams = [item for item in streams if item.get("codec_type") == "video"]
        audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
        video = video_streams[0] if video_streams else {}
        duration = _float(fmt.get("duration", probed.get("duration")))
        if duration is None:
            durations = [_float(item.get("duration")) for item in streams]
            duration = next((item for item in durations if item is not None), None)
        frame_count = _int(video.get("nb_read_frames", video.get("nb_frames")))
        width, height = _int(video.get("width")), _int(video.get("height"))
        fps_value = video.get("avg_frame_rate", video.get("r_frame_rate"))
        fps = None
        if isinstance(fps_value, str) and "/" in fps_value:
            try:
                left, right = fps_value.split("/", 1)
                fps = float(left) / float(right)
            except (ValueError, ZeroDivisionError):
                fps = None
        else:
            fps = _float(fps_value)
        metadata.update({"duration": duration, "width": width, "height": height, "frame_count": frame_count, "fps": fps, "audio_streams": len(audio_streams), "has_audio": bool(audio_streams)})
        _add(checks, violations, "container", not probe_error and bool(fmt or streams), "invalid_container", "Media container could not be safely probed." + (f" {probe_error}." if probe_error else ""), verification="local_container_probe")
        _add(checks, violations, "duration_finite", duration is not None and duration > 0 and (bound.max_duration is None or duration <= bound.max_duration), "duration_invalid_or_out_of_bounds", "Media duration is missing, non-positive, non-finite, or exceeds the configured bound.", {"min": "> 0", "max": bound.max_duration}, duration)
        if media_kind == "video":
            _add(checks, violations, "video_stream", bool(video_streams), "missing_video_stream", "Video input contains no decodable video stream.", verification="local_container_probe")
            sane_dimensions = width is not None and height is not None and width > 0 and height > 0 and width <= bound.max_width and height <= bound.max_height and width * height <= bound.max_pixels
            _add(checks, violations, "dimensions_sane", sane_dimensions, "dimensions_out_of_bounds", "Video dimensions are missing, zero, or exceed the configured bounds.", {"max_width": bound.max_width, "max_height": bound.max_height, "max_pixels": bound.max_pixels}, {"width": width, "height": height})
            if frame_count is None and video_streams:
                first_ok, first_data, first_error = _decode(file_path, "0:v:0", bound.timeout_seconds, first_frame=True)
                if first_ok and first_data:
                    frame_count = 1
                    metadata["frame_count"] = 1
                else:
                    _add(checks, violations, "frame_count", False, "zero_or_unknown_frames", "Video has no provable decodable frame count." + (f" {first_error}." if first_error else ""), verification="decoded_video_frame")
            _add(checks, violations, "frame_count", frame_count is not None and 0 < frame_count <= bound.max_frames, "zero_or_excessive_frames", "Video has zero frames or exceeds the frame bound.", {"min": 1, "max": bound.max_frames}, frame_count)
            decoded, _, detail = _decode(file_path, "0:v:0", bound.timeout_seconds)
            _add(checks, violations, "video_decode", decoded, "undecodable_frames", "Video frames could not be fully decoded." + (f" {detail}." if detail else ""), verification="decoded_video_frames")
        else:
            _add(checks, violations, "audio_stream", bool(audio_streams), "missing_audio_stream", "Audio input contains no audio stream.", verification="local_container_probe")
            decoded, _, detail = _decode(file_path, "0:a:0", bound.timeout_seconds)
            _add(checks, violations, "audio_decode", decoded, "undecodable_audio", "Audio stream could not be decoded." + (f" {detail}." if detail else ""), verification="decoded_audio_stream")
        if audio_streams:
            decoded_audio, _, detail = _decode(file_path, "0:a:0", bound.timeout_seconds)
            _add(checks, violations, "audio_stream_decode", decoded_audio, "undecodable_audio", "Present audio stream could not be decoded." + (f" {detail}." if detail else ""), verification="decoded_audio_stream")
        if expectation.require_audio or expectation.required_audio_streams is not None:
            required = expectation.required_audio_streams or 1
            _add(checks, violations, "required_audio", len(audio_streams) >= required, "missing_required_audio", "Required audio stream is missing or the stream count is too low.", {"minimum_streams": required}, len(audio_streams), verification="local_container_probe")
        if expectation.require_audio_signal:
            signal, detail = _audio_signal(file_path, bound.timeout_seconds)
            metadata["audio_has_signal"] = signal
            _add(checks, violations, "audio_signal", signal is True, "silent_or_undecodable_audio", "Required audio is silent or its decoded signal could not be verified." + (f" {detail}." if detail else ""), True, signal, verification="decoded_audio_signal", status=None if signal is not None else "unverifiable")

    if expectation.duration is not None:
        actual = metadata.get("duration")
        tolerance = _float(expectation.duration_tolerance)
        passed = actual is not None and tolerance is not None and abs(actual - float(expectation.duration)) <= tolerance
        _add(checks, violations, "expected_duration", passed, "duration_mismatch", "Candidate duration does not satisfy the expected duration tolerance.", {"seconds": expectation.duration, "tolerance": tolerance}, actual)
    if expectation.width is not None or expectation.height is not None:
        actual = {"width": metadata.get("width"), "height": metadata.get("height")}
        passed = actual["width"] is not None and actual["height"] is not None and (expectation.width is None or actual["width"] == expectation.width) and (expectation.height is None or actual["height"] == expectation.height)
        _add(checks, violations, "expected_dimensions", passed, "dimensions_mismatch", "Candidate dimensions do not satisfy the expected dimensions.", {"width": expectation.width, "height": expectation.height}, actual)
    if expectation.aspect is not None:
        actual = _ratio(metadata)
        passed = _aspect_matches(actual, expectation.aspect, expectation.aspect_tolerance)
        _add(checks, violations, "expected_aspect", passed, "aspect_mismatch", "Candidate aspect does not satisfy the expected aspect.", {"aspect": expectation.aspect, "tolerance": expectation.aspect_tolerance}, actual)
    return MediaQualityReport(not violations, media_kind, display_path, metadata, tuple(checks), tuple(violations))


def _ratio(values: Mapping[str, Any]) -> float | None:
    width, height = values.get("width"), values.get("height")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)) or width <= 0 or height <= 0:
        return None
    result = float(width) / float(height)
    return result if math.isfinite(result) else None


def enforce_media_quality(*args: Any, **kwargs: Any) -> MediaQualityReport:
    report = preflight_media(*args, **kwargs)
    if not report.passed:
        raise MediaQualityError(report)
    return report


check_media_quality = preflight_media
quality_gate = preflight_media


def _candidate_path(candidate: Any, kind: str | None) -> tuple[Path | None, str, dict[str, Any]]:
    if isinstance(candidate, (str, Path)):
        path = Path(candidate)
        return path, kind or _kind(path, None), {}
    if isinstance(candidate, Mapping):
        details = candidate.get("details") if isinstance(candidate.get("details"), Mapping) else candidate
        path = candidate.get("path")
        if path is not None:
            path = Path(path)
        return path, kind or str(candidate.get("kind") or _kind(path or Path("candidate"), None)), dict(details)
    path = getattr(candidate, "path", None)
    details = getattr(candidate, "details", {})
    path = Path(path) if path is not None else None
    return path, kind or str(getattr(candidate, "kind", None) or _kind(path or Path("candidate"), None)), dict(details) if isinstance(details, Mapping) else {}


def pre_evaluation_gate(candidate: Any, kind: str | None = None, *, constraints: Any = None, baseline: Any = None, limits: MediaQualityLimits | Mapping[str, Any] | None = None) -> PreEvaluationReport:
    """Run media and locked-constraint checks in order before an evaluator."""
    path, media_kind, candidate_details = _candidate_path(candidate, kind)
    from .constraints import CreativeConstraints

    contract = CreativeConstraints.from_mapping(constraints) if constraints is not None else None
    baseline_details: dict[str, Any] = {}
    baseline_path: Path | None = None
    if baseline is not None:
        baseline_path, _, baseline_details = _candidate_path(baseline, media_kind)
    expectation = contract.quality_expectation(baseline_details) if contract is not None else None
    if path is None:
        quality = MediaQualityReport(False, media_kind, "", violations=("Candidate must provide a local media path for pre-evaluation quality checks.",))
        return PreEvaluationReport(False, quality)
    quality = preflight_media(path, media_kind, expected=expectation, limits=limits)
    if not quality.passed:
        return PreEvaluationReport(False, quality)
    if baseline_path is not None and not baseline_details:
        baseline_quality = preflight_media(baseline_path, media_kind, limits=limits)
        if not baseline_quality.passed:
            return PreEvaluationReport(False, baseline_quality)
        baseline_details = baseline_quality.metadata
    if contract is None:
        return PreEvaluationReport(True, quality)
    # Decoded file facts are authoritative for media properties while editable
    # manifests remain authoritative for copy/logo/object constraints.
    candidate_details = {**candidate_details, **quality.metadata}
    if baseline_details:
        baseline_details = dict(baseline_details)
    constraint_report = contract.check(candidate_details, baseline_details or baseline)
    return PreEvaluationReport(constraint_report.passed, quality, constraint_report)


def evaluate_after_gate(candidate: Any, evaluator: Callable[[Any], Any], kind: str | None = None, *, constraints: Any = None, baseline: Any = None, limits: MediaQualityLimits | Mapping[str, Any] | None = None) -> Any:
    """Call ``evaluator`` only after all cheap gates have passed."""
    report = pre_evaluation_gate(candidate, kind, constraints=constraints, baseline=baseline, limits=limits)
    if not report.passed:
        raise PreEvaluationRejected(report)
    return evaluator(candidate)


evaluate_with_quality_gate = evaluate_after_gate


__all__ = ["MediaQualityError", "MediaQualityLimits", "MediaExpectation", "MediaQualityReport", "PreEvaluationReport", "PreEvaluationRejected", "preflight_media", "enforce_media_quality", "check_media_quality", "quality_gate", "pre_evaluation_gate", "evaluate_after_gate", "evaluate_with_quality_gate"]
