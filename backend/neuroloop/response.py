"""Versioned TSAM/Kragel evidence contracts and temporal target scoring.

TSAM is an independent direct-media audiovisual readout.  Kragel is an
experimental pattern-expression readout derived from a TRIBE cortical
prediction.  Both are relative model evidence, not calibrated human-emotion
probabilities.  The worker-facing ``ensemble(evidence)`` and
``target_score(report, target)`` calls remain backwards compatible; the
additional axis and provenance fields are additive.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any


# This order is the order in the published TSAM setup code.  It is part of the
# checkpoint contract and must not be alphabetized or inferred from a dict.
COMMON = (
    "happiness", "surprise", "fear", "sadness", "anger", "neutral", "contempt", "disgust",
)
TSAM_LABELS = (
    "Anger", "Contempt", "Disgust", "Fear", "Happiness", "Neutral", "Sadness", "Surprise",
)
TSAM_MAP = dict(zip(TSAM_LABELS, ("anger", "contempt", "disgust", "fear", "happiness", "neutral", "sadness", "surprise")))
KRAGEL_LABELS = ("amused", "angry", "content", "fearful", "neutral", "sad", "surprised")
KRAGEL_MAP = {
    "amused": "happiness", "content": "happiness", "angry": "anger", "fearful": "fear",
    "neutral": "neutral", "sad": "sadness", "surprised": "surprise",
}

ENSEMBLE_PROFILE = "tsam55-kragel45-relative-evidence-v1"
ENSEMBLE_VERSION = "response-ensemble/v1"
SCORING_PROFILE = "response-target-distance/v1"
SCORING_VERSION = "response-scoring/v1"
PROVENANCE_VERSION = "response-provenance/v1"
TIME_AXIS_VERSION = "normalized-interval-axis/v1"
DEFAULT_SOURCE_WEIGHTS = {"tsam": 0.55, "kragel": 0.45}


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _softmax(values: Iterable[float], temperature: float = 1.0) -> list[float]:
    temperature = _finite(temperature, "temperature")
    if temperature <= 0:
        raise ValueError("temperature must be greater than zero")
    numbers = [_finite(value, "logit") for value in values]
    if not numbers:
        return []
    peak = max(numbers)
    exponentials = [math.exp((value - peak) / temperature) for value in numbers]
    total = math.fsum(exponentials)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("logits cannot produce a finite softmax")
    result = [value / total for value in exponentials]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("softmax produced non-finite evidence")
    return result


def normalized_axis(
    intervals: Iterable[Mapping[str, Any] | tuple[float, float]],
    source_duration: float,
    *,
    source: str,
) -> list[dict[str, Any]]:
    """Validate source intervals and add a shared [0, 1] time axis.

    Intervals are allowed to be non-uniform and overlapping.  Consumers use
    explicit duration overlap when combining sources.  Missing intervals are
    represented by missing coverage, never by zero-valued evidence.
    """
    duration = _finite(source_duration, "source duration")
    if duration <= 0:
        raise ValueError("source duration must be greater than zero")
    axis: list[dict[str, Any]] = []
    for index, item in enumerate(intervals):
        if isinstance(item, Mapping):
            start = _finite(item.get("start"), f"{source} interval {index} start")
            end = _finite(item.get("end"), f"{source} interval {index} end")
        else:
            try:
                start = _finite(item[0], f"{source} interval {index} start")
                end = _finite(item[1], f"{source} interval {index} end")
            except (TypeError, IndexError) as exc:
                raise ValueError(f"{source} interval {index} needs start and end") from exc
        if start < 0 or end <= start:
            raise ValueError(f"{source} interval {index} must satisfy 0 <= start < end")
        if end > duration + 1e-9:
            raise ValueError(f"{source} interval {index} exceeds source duration")
        end = min(end, duration)
        axis.append({
            "index": index,
            "source": source,
            "start": start,
            "end": end,
            "duration": end - start,
            "start_norm": start / duration,
            "end_norm": end / duration,
            "axis_version": TIME_AXIS_VERSION,
        })
    return axis


def _validate_values(values: Mapping[str, Any], *, label: str) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for name, value in values.items():
        if name not in COMMON:
            raise ValueError(f"{label} contains unsupported dimension {name!r}")
        result[name] = None if value is None else _finite(value, f"{label}.{name}")
    return result


def _validate_tsam_labels(labels: Any) -> list[str]:
    if list(labels or []) != list(TSAM_LABELS):
        raise ValueError("TSAM class order must be exactly " + ", ".join(TSAM_LABELS))
    return list(TSAM_LABELS)


def tsam_series(result: dict | None) -> list[dict[str, Any]]:
    """Validate TSAM windows and return finite canonical source rows."""
    if not result or result.get("status") != "experimental":
        return []
    labels = _validate_tsam_labels(result.get("labels"))
    windows = result.get("windows")
    if not isinstance(windows, list):
        raise ValueError("Experimental TSAM evidence must contain a windows list")
    if not windows:
        return []
    intervals: list[dict[str, float]] = []
    logits_rows: list[list[float]] = []
    for index, window in enumerate(windows):
        if not isinstance(window, Mapping):
            raise ValueError(f"TSAM window {index} must be an object")
        # Pre-contract saved evidence omitted timestamps.  Its historical
        # windows were fixed, non-overlapping five-second rows; infer only
        # when both endpoints are absent.  A partially specified interval is
        # malformed and must fail closed.
        if "start" not in window and "end" not in window:
            start, end = float(index * 5), float(index * 5 + 5)
        elif "start" not in window or "end" not in window:
            raise ValueError(f"TSAM window {index} must specify both start and end")
        else:
            start = _finite(window.get("start"), f"TSAM window {index} start")
            end = _finite(window.get("end"), f"TSAM window {index} end")
        if start < 0 or end <= start:
            raise ValueError(f"TSAM window {index} must satisfy 0 <= start < end")
        logits = window.get("logits")
        if not isinstance(logits, (list, tuple)) or len(logits) != len(labels):
            raise ValueError(f"TSAM window {index} must contain exactly eight logits")
        intervals.append({"start": start, "end": end})
        logits_rows.append([_finite(value, f"TSAM window {index} logit") for value in logits])
    source_duration = result.get("source_duration")
    if source_duration is None:
        source_duration = max(item["end"] for item in intervals)
    axis = normalized_axis(intervals, source_duration, source="tsam")
    rows: list[dict[str, Any]] = []
    for item, logits in zip(axis, logits_rows):
        probabilities = _softmax(logits)
        rows.append({
            **item,
            "logits": logits,
            "values": {TSAM_MAP[label]: value for label, value in zip(labels, probabilities)},
        })
    return rows


def tsam_relative(result: dict | None) -> dict[str, float] | None:
    if not result or result.get("status") != "experimental":
        return None
    rows = tsam_series(result)
    if not rows:
        raise ValueError("Experimental TSAM evidence has no complete windows")
    return {
        name: math.fsum(float(row["values"][name]) for row in rows) / len(rows)
        for name in COMMON
    }


def _kragel_values(aggregate: Mapping[str, Any]) -> dict[str, float | None]:
    if not isinstance(aggregate, Mapping) or not aggregate:
        raise ValueError("Experimental Kragel evidence must contain an aggregate")
    unsupported = set(aggregate) - set(KRAGEL_LABELS)
    if unsupported:
        raise ValueError("Kragel aggregate contains unsupported dimensions: " + ", ".join(sorted(unsupported)))
    labels = [label for label in KRAGEL_LABELS if label in aggregate]
    probabilities = _softmax([_finite(aggregate[label], f"Kragel aggregate.{label}") for label in labels], temperature=0.12)
    output: dict[str, float | None] = {name: None for name in COMMON}
    for label, value in zip(labels, probabilities):
        name = KRAGEL_MAP[label]
        output[name] = value if output[name] is None else float(output[name]) + value
    return output


def kragel_relative(result: dict | None) -> dict[str, float | None] | None:
    """Return Kragel evidence; unsupported contempt/disgust stay ``None``."""
    if not result or result.get("status") != "experimental":
        return None
    return _kragel_values(result.get("aggregate") or {})


def kragel_series(result: dict | None) -> list[dict[str, Any]]:
    """Validate per-row Kragel values and use its explicit TRIBE time axis."""
    if not result or result.get("status") != "experimental":
        return []
    trajectories = result.get("trajectories")
    if not isinstance(trajectories, Mapping) or not trajectories:
        return []
    unsupported = set(trajectories) - set(KRAGEL_LABELS)
    if unsupported:
        raise ValueError("Kragel trajectories contain unsupported dimensions: " + ", ".join(sorted(unsupported)))
    if any(not isinstance(values, list) for values in trajectories.values()):
        raise ValueError("Kragel trajectories must be lists")
    lengths = {len(values) for values in trajectories.values()}
    if len(lengths) != 1:
        raise ValueError("Kragel trajectories must have equal row counts")
    count = lengths.pop()
    if count == 0:
        return []
    raw_axis = result.get("time_axis")
    if not isinstance(raw_axis, list) or len(raw_axis) != count:
        raise ValueError("Temporal Kragel evidence requires an explicit time_axis")
    source_duration = result.get("source_duration")
    if source_duration is None:
        source_duration = max(_finite(item.get("end"), "Kragel time_axis end") for item in raw_axis)
    axis = normalized_axis(
        [{"start": item.get("start"), "end": item.get("end")} for item in raw_axis],
        source_duration,
        source="kragel",
    )
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(axis):
        aggregate = {
            label: _finite(trajectories.get(label, [])[index], f"Kragel trajectory {label}[{index}]")
            for label in KRAGEL_LABELS
        }
        rows.append({**item, "values": _kragel_values(aggregate)})
    return rows


def _interval_union_length(intervals: list[tuple[float, float]]) -> float:
    """Return the length of an interval union without double-counting overlap."""
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start
        current_start, current_end = start, end
    return total + current_end - current_start


def _source_window_details(
    rows: list[dict[str, Any]], start: float, end: float,
) -> tuple[dict[str, float | None] | None, float, dict[str, float]]:
    """Aggregate rows over a target interval using interval-union coverage.

    Rows can overlap.  The interval union defines support, while each atomic
    sub-interval is represented exactly once.  If multiple rows are active in
    the same atomic interval, their finite values are averaged there; their
    durations are not counted repeatedly.  Coverage is returned for the source
    and for every supported dimension separately so missing dimensions cannot
    be mistaken for zero evidence.
    """
    if not 0 <= start < end <= 1:
        raise ValueError("Normalized target window must satisfy 0 <= start < end <= 1")
    target_duration = end - start
    intervals: list[tuple[float, float, dict[str, float | None]]] = []
    for index, row in enumerate(rows):
        row_start = _finite(row.get("start_norm"), f"source interval {index} start_norm")
        row_end = _finite(row.get("end_norm"), f"source interval {index} end_norm")
        if not 0 <= row_start < row_end <= 1:
            raise ValueError(f"source interval {index} must satisfy 0 <= start_norm < end_norm <= 1")
        clipped_start = max(start, row_start)
        clipped_end = min(end, row_end)
        if clipped_end > clipped_start:
            intervals.append((clipped_start, clipped_end, _validate_values(row.get("values") or {}, label="source interval values")))
    source_union = _interval_union_length([(left, right) for left, right, _ in intervals])
    source_coverage = min(1.0, source_union / target_duration)
    dimension_coverage: dict[str, float] = {}
    values: dict[str, float | None] = {}
    for name in COMMON:
        supported = [(left, right, row_values[name]) for left, right, row_values in intervals if row_values.get(name) is not None]
        dimension_union = _interval_union_length([(left, right) for left, right, _ in supported])
        dimension_coverage[name] = min(1.0, dimension_union / target_duration)
        if dimension_union <= 0:
            values[name] = None
            continue
        boundaries = {left for left, right, _ in supported} | {right for left, right, _ in supported}
        ordered = sorted(boundaries)
        numerator = 0.0
        for left, right in zip(ordered, ordered[1:]):
            if right <= left:
                continue
            midpoint = (left + right) / 2
            active = [value for row_left, row_right, value in supported if row_left <= midpoint < row_right]
            if active:
                # The atomic interval is counted once even when several rows
                # overlap.  Equal weighting is deterministic and source-local.
                numerator += (right - left) * (math.fsum(float(value) for value in active) / len(active))
        values[name] = numerator / dimension_union
    if source_union <= 0:
        return None, 0.0, dimension_coverage
    return values, source_coverage, dimension_coverage


def _source_window_values(rows: list[dict[str, Any]], start: float, end: float) -> tuple[dict[str, float | None] | None, float]:
    """Compatibility wrapper returning values and aggregate source coverage."""
    values, coverage, _ = _source_window_details(rows, start, end)
    return values, coverage


def _combine_source_values(
    source_values: Mapping[str, Mapping[str, Any] | None],
    *,
    weights: Mapping[str, float] | None = None,
    coverage: Mapping[str, float] | None = None,
    dimension_coverage: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, float | None] | None:
    weights = weights or DEFAULT_SOURCE_WEIGHTS
    output: dict[str, float | None] = {}
    has_value = False
    for emotion in COMMON:
        pieces: list[tuple[float, float]] = []
        for source in ("tsam", "kragel"):
            values = source_values.get(source)
            if not values or values.get(emotion) is None:
                continue
            weight = float(weights.get(source, 0.0))
            if dimension_coverage is not None:
                weight *= max(0.0, min(1.0, float(dimension_coverage.get(source, {}).get(emotion, 0.0))))
            elif coverage is not None:
                weight *= max(0.0, min(1.0, float(coverage.get(source, 0.0))))
            if weight > 0:
                pieces.append((weight, _finite(values[emotion], f"{source}.{emotion}")))
        total = math.fsum(weight for weight, _ in pieces)
        output[emotion] = math.fsum(weight * value for weight, value in pieces) / total if total else None
        has_value = has_value or total > 0
    return output if has_value else None


def _merged_series(tsam_rows: list[dict[str, Any]], kragel_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundaries = {0.0, 1.0}
    for row in tsam_rows + kragel_rows:
        boundaries.update((float(row["start_norm"]), float(row["end_norm"])))
    points = sorted(boundaries)
    merged: list[dict[str, Any]] = []
    for start, end in zip(points, points[1:]):
        if end <= start:
            continue
        source_values: dict[str, Mapping[str, Any] | None] = {}
        coverage: dict[str, float] = {}
        dimension_coverage: dict[str, dict[str, float]] = {}
        if tsam_rows:
            source_values["tsam"], coverage["tsam"], dimension_coverage["tsam"] = _source_window_details(tsam_rows, start, end)
        if kragel_rows:
            source_values["kragel"], coverage["kragel"], dimension_coverage["kragel"] = _source_window_details(kragel_rows, start, end)
        values = _combine_source_values(source_values, coverage=coverage, dimension_coverage=dimension_coverage)
        if values is not None:
            merged.append({
                "index": len(merged), "source": "ensemble", "start_norm": start,
                "end_norm": end, "duration_norm": end - start, "values": values,
                "source_coverage": coverage, "source_dimension_coverage": dimension_coverage,
                "axis_version": TIME_AXIS_VERSION,
            })
    return merged


def _temporal_window_details(
    source_series: Mapping[str, Any],
    start: float,
    end: float,
    weights: Mapping[str, float],
) -> tuple[dict[str, float | None] | None, dict[str, float], dict[str, float], dict[str, dict[str, float]]]:
    """Combine temporal sources and compute union support across all sources."""
    source_values: dict[str, Mapping[str, Any] | None] = {}
    source_coverage: dict[str, float] = {}
    source_dimension_coverage: dict[str, dict[str, float]] = {}
    rows_by_source: dict[str, list[dict[str, Any]]] = {}
    for source in ("tsam", "kragel"):
        rows = source_series.get(source) or []
        if not rows:
            continue
        rows_by_source[source] = rows
        source_values[source], source_coverage[source], source_dimension_coverage[source] = _source_window_details(rows, start, end)
    actual = _combine_source_values(
        source_values,
        weights=weights,
        coverage=source_coverage,
        dimension_coverage=source_dimension_coverage,
    )
    target_duration = end - start
    combined_dimension_coverage: dict[str, float] = {}
    for name in COMMON:
        supported: list[tuple[float, float]] = []
        for rows in rows_by_source.values():
            for index, row in enumerate(rows):
                row_start = _finite(row.get("start_norm"), f"source interval {index} start_norm")
                row_end = _finite(row.get("end_norm"), f"source interval {index} end_norm")
                if not 0 <= row_start < row_end <= 1:
                    raise ValueError(f"source interval {index} must satisfy 0 <= start_norm < end_norm <= 1")
                values = _validate_values(row.get("values") or {}, label="source interval values")
                if values.get(name) is not None:
                    left, right = max(start, row_start), min(end, row_end)
                    if right > left:
                        supported.append((left, right))
        combined_dimension_coverage[name] = min(1.0, _interval_union_length(supported) / target_duration)
    return actual, source_coverage, combined_dimension_coverage, source_dimension_coverage


def _validate_weights(weights: Mapping[str, Any]) -> dict[str, float]:
    if set(weights) != set(DEFAULT_SOURCE_WEIGHTS):
        raise ValueError("Ensemble weights must specify exactly TSAM and Kragel")
    result = {name: _finite(value, f"weight.{name}") for name, value in weights.items()}
    if any(value < 0 for value in result.values()):
        raise ValueError("Ensemble weights cannot be negative")
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError("Ensemble weights must sum to one")
    if not any(result.values()):
        raise ValueError("At least one ensemble weight must be positive")
    return result


def _source_provenance(name: str, result: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(result, Mapping) and isinstance(result.get("provenance"), Mapping):
        return dict(result["provenance"])
    checkpoint_hash = result.get("weights_sha256") or result.get("checkpoint_sha256") if isinstance(result, Mapping) else None
    profile = result.get("profile") if isinstance(result, Mapping) else None
    return {
        "contract_version": PROVENANCE_VERSION, "source": name,
        "model": {"name": name, "version": profile},
        "checkpoint": {"sha256": checkpoint_hash, "version": profile},
        "preprocessing": {"version": profile, "sha256": None},
        "geometry": {"version": None, "sha256": None},
        "projection": {"version": None, "sha256": None},
        "legacy_record_without_provenance": True,
    }


def _ensemble_provenance(results: Mapping[str, Mapping[str, Any] | None], weights: Mapping[str, float], profile: str) -> dict[str, Any]:
    specification = {
        "version": ENSEMBLE_VERSION, "profile": profile,
        "source_weights": dict(weights),
        "source_semantics": {"tsam": "direct_media", "kragel": "tribe_derived"},
        "unsupported_dimensions": {"kragel": ["contempt", "disgust"]},
    }
    ensemble_hash = _canonical_hash(specification)
    return {
        "contract_version": PROVENANCE_VERSION,
        "model": {name: _source_provenance(name, value).get("model") for name, value in results.items()},
        "checkpoint": {name: _source_provenance(name, value).get("checkpoint") for name, value in results.items()},
        "preprocessing": {name: _source_provenance(name, value).get("preprocessing") for name, value in results.items()},
        "geometry": {name: _source_provenance(name, value).get("geometry") for name, value in results.items()},
        "projection": {name: _source_provenance(name, value).get("projection") for name, value in results.items()},
        "ensemble": {**specification, "version": ENSEMBLE_VERSION, "sha256": ensemble_hash},
    }


def ensemble(evidence: dict[str, Any], *, weights: Mapping[str, Any] | None = None, profile: str = ENSEMBLE_PROFILE) -> dict[str, Any]:
    """Combine available sources under a fixed, versioned profile."""
    if not isinstance(evidence, Mapping):
        raise ValueError("Response evidence must be an object")
    configured = _validate_weights(weights or DEFAULT_SOURCE_WEIGHTS)
    if weights is not None and configured != DEFAULT_SOURCE_WEIGHTS and not re.search(r"(?:^|[-_/])v\d+(?:$|[-_.])", profile):
        raise ValueError("Custom ensemble weights require an explicitly versioned profile")

    tsam_result = evidence.get("tsam")
    kragel_result = evidence.get("kragel")
    if isinstance(tsam_result, Mapping) and tsam_result.get("source_kind") not in (None, "direct_media"):
        raise ValueError("TSAM evidence must remain direct_media evidence")
    if isinstance(kragel_result, Mapping) and kragel_result.get("source_kind") not in (None, "tribe_derived"):
        raise ValueError("Kragel evidence must remain TRIBE-derived evidence")
    tsam = tsam_relative(tsam_result) if tsam_result and tsam_result.get("status") == "experimental" else None
    kragel = kragel_relative(kragel_result) if kragel_result and kragel_result.get("status") == "experimental" else None
    tsam_rows = tsam_series(tsam_result) if tsam is not None else []
    kragel_rows = kragel_series(kragel_result) if kragel is not None else []
    active = [name for name, value in (("tsam", tsam), ("kragel", kragel)) if value is not None]
    values = _combine_source_values({"tsam": tsam, "kragel": kragel}, weights=configured) or {name: None for name in COMMON}
    disagreement: dict[str, float] = {}
    if tsam is not None and kragel is not None:
        for name in COMMON:
            if tsam.get(name) is not None and kragel.get(name) is not None:
                disagreement[name] = abs(float(tsam[name]) - float(kragel[name]))
    mean_disagreement = math.fsum(disagreement.values()) / len(disagreement) if disagreement else None
    results = {"tsam": tsam_result, "kragel": kragel_result}
    return {
        "version": ENSEMBLE_VERSION, "profile": profile, "values": values,
        "sources": {"tsam": tsam, "kragel": kragel},
        "source_semantics": {"tsam": "direct_media", "kragel": "tribe_derived"},
        "source_weights": {name: configured[name] if name in active else 0.0 for name in configured},
        "active_sources": active, "unsupported_dimensions": {"kragel": ["contempt", "disgust"]},
        "disagreement": disagreement, "mean_disagreement": mean_disagreement,
        "confidence": "moderate" if len(active) == 2 and (mean_disagreement or 0) < 0.25 else "low",
        "time_axis": {
            "version": TIME_AXIS_VERSION, "normalization": "source_duration",
            "missing_policy": "omit_uncovered_intervals; never substitute zero",
            "overlap_policy": "duration_weighted_source_overlap",
        },
        "source_series": {"tsam": tsam_rows or None, "kragel": kragel_rows or None},
        "series": _merged_series(tsam_rows, kragel_rows),
        "provenance": _ensemble_provenance(results, configured, profile),
        "interpretation": "Relative model evidence combined transparently across available TSAM and Kragel sources; not calibrated human emotion probabilities.",
    }


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, Mapping):
            return dict(dumped)
    raise ValueError("Target must be a mapping or a Pydantic target model")


def _target_windows(target: Any) -> list[dict[str, Any]]:
    payload = _as_mapping(target)
    if not payload:
        return []
    emotions = payload.get("emotions") or {}
    windows = payload.get("windows") or payload.get("time_windows") or payload.get("segments")
    explicit = payload.get("time_window") or payload.get("window")
    if windows and explicit:
        raise ValueError("A target cannot specify both one time_window and windows")
    if windows:
        if not isinstance(windows, list):
            raise ValueError("Target windows must be a list")
        result = []
        for index, item in enumerate(windows):
            if not isinstance(item, Mapping):
                raise ValueError(f"Target window {index} must be an object")
            result.append({
                "id": str(item.get("id") or item.get("window_id") or f"window-{index + 1}"),
                "start": _finite(item.get("start"), f"target window {index} start"),
                "end": _finite(item.get("end"), f"target window {index} end"),
                "weight": _finite(item.get("weight", 1.0), f"target window {index} weight"),
                "emotions": item.get("emotions") or emotions,
            })
        return result
    if explicit:
        if not isinstance(explicit, Mapping):
            raise ValueError("Target time_window must be an object")
        return [{
            "id": str(explicit.get("id") or "time-window"),
            "start": _finite(explicit.get("start"), "target time_window start"),
            "end": _finite(explicit.get("end"), "target time_window end"),
            "weight": _finite(explicit.get("weight", 1.0), "target time_window weight"),
            "emotions": emotions,
        }]
    return [{"id": "whole-creative", "start": 0.0, "end": 1.0, "weight": 1.0, "emotions": emotions}]


def _score_values(actual: Mapping[str, Any] | None, requested: Mapping[str, Any], disagreement: float | None) -> dict[str, Any] | None:
    if not actual or not requested:
        return None
    weighted_error = 0.0
    weight_total = 0.0
    dimensions = []
    for emotion, specification in requested.items():
        if emotion not in COMMON:
            raise ValueError(f"Target contains unsupported dimension {emotion!r}")
        if isinstance(specification, Mapping):
            desired = _finite(specification.get("desired", 0.5), f"target.{emotion}.desired")
            weight = _finite(specification.get("weight", 1.0), f"target.{emotion}.weight")
        else:
            desired, weight = _finite(specification, f"target.{emotion}.desired"), 1.0
        if not 0 <= desired <= 1:
            raise ValueError(f"target.{emotion}.desired must be between zero and one")
        if weight <= 0:
            raise ValueError(f"target.{emotion}.weight must be greater than zero")
        value = actual.get(emotion)
        if value is None:
            continue
        value = _finite(value, f"actual.{emotion}")
        error = abs(value - desired)
        weighted_error += weight * error
        weight_total += weight
        dimensions.append({"emotion": emotion, "desired": desired, "actual": value, "weight": weight, "error": error})
    if weight_total == 0:
        return None
    raw_match = max(0.0, 1.0 - weighted_error / weight_total)
    penalty = min(0.15, max(0.0, _finite(disagreement or 0.0, "disagreement")) * 0.2)
    return {
        "value": max(0.0, raw_match - penalty), "raw_match": raw_match,
        "disagreement_penalty": penalty, "dimensions": dimensions,
    }


def _window_disagreement(report: Mapping[str, Any], start: float, end: float) -> float | None:
    source_series = report.get("source_series")
    if not isinstance(source_series, Mapping):
        return report.get("mean_disagreement")
    tsam_rows, kragel_rows = source_series.get("tsam") or [], source_series.get("kragel") or []
    if not tsam_rows or not kragel_rows:
        return None
    tsam, tsam_coverage = _source_window_values(tsam_rows, start, end)
    kragel, kragel_coverage = _source_window_values(kragel_rows, start, end)
    if not tsam or not kragel or not tsam_coverage or not kragel_coverage:
        return None
    differences = [abs(float(tsam[name]) - float(kragel[name])) for name in COMMON if tsam.get(name) is not None and kragel.get(name) is not None]
    return math.fsum(differences) / len(differences) if differences else None


def target_score(report: dict | None, target: dict | Any | None) -> dict | None:
    """Score whole-creative or normalized time-window targets.

    Temporal targets never fall back to report-wide values.  Consequently a
    candidate change outside a requested segment cannot satisfy that segment's
    target merely by improving another segment.
    """
    if not report or not isinstance(report, Mapping):
        return None
    windows = _target_windows(target)
    if not windows:
        return None
    source_series = report.get("source_series")
    scored_segments: list[dict[str, Any]] = []
    for window in windows:
        start, end = window["start"], window["end"]
        if not 0 <= start < end <= 1:
            raise ValueError("Target windows must satisfy 0 <= start < end <= 1")
        if not isinstance(window["emotions"], Mapping):
            raise ValueError(f"Target window {window['id']} emotions must be an object")
        unsupported = set(window["emotions"]) - set(COMMON)
        if unsupported:
            raise ValueError("Target contains unsupported dimension(s): " + ", ".join(sorted(unsupported)))
        whole = window["id"] == "whole-creative" and start == 0 and end == 1
        coverage = 1.0
        if whole:
            actual = report.get("values")
        else:
            if not isinstance(source_series, Mapping):
                raise ValueError("Temporal target requires an explicit response time axis")
            scoring_weights = report.get("source_weights") or DEFAULT_SOURCE_WEIGHTS
            for source, weight in scoring_weights.items():
                if source in ("tsam", "kragel") and (_finite(weight, f"source weight.{source}") < 0):
                    raise ValueError("Source weights cannot be negative")
            actual, source_coverage, coverage_by_dimension, source_dimension_coverage = _temporal_window_details(
                source_series, start, end, scoring_weights,
            )
            if actual is None:
                return None
            requested_names = list(window["emotions"])
            if not requested_names or any(coverage_by_dimension.get(name, 0.0) < 1.0 - 1e-9 for name in requested_names):
                # A target segment with a gap is not scoreable.  Returning a
                # partial numeric match would let a candidate satisfy a target
                # using only the observed portion of that segment.
                return None
            coverage = min(coverage_by_dimension[name] for name in requested_names)
        scored = _score_values(actual, window["emotions"], _window_disagreement(report, start, end))
        if scored is None:
            return None
        segment = {"id": window["id"], "window": [start, end], "coverage": coverage, "weight": window["weight"], **scored}
        if not whole:
            segment.update({
                "fully_supported": True,
                "source_coverage": source_coverage,
                "source_dimension_coverage": source_dimension_coverage,
                "dimension_coverage": coverage_by_dimension,
            })
        scored_segments.append(segment)
    if not scored_segments:
        return None
    weights = [max(0.0, _finite(item["weight"], "target window weight")) for item in scored_segments]
    if not any(weights):
        raise ValueError("At least one target window weight must be positive")
    total = math.fsum(weights)
    value = math.fsum(item["value"] * weight for item, weight in zip(scored_segments, weights)) / total
    raw_match = math.fsum(item["raw_match"] * weight for item, weight in zip(scored_segments, weights)) / total
    penalty = math.fsum(item["disagreement_penalty"] * weight for item, weight in zip(scored_segments, weights)) / total
    return {
        "metric": SCORING_PROFILE, "version": SCORING_VERSION, "value": value,
        "raw_match": raw_match, "disagreement_penalty": penalty,
        "dimensions": [dimension for item in scored_segments for dimension in item["dimensions"]],
        "segments": scored_segments, "scale": [0, 1],
        "interpretation": "Closeness of relative TSAM/Kragel model evidence to the declared target. This is an optimization score, not a measured human response rate.",
    }
