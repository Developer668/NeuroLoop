"""Transparent TSAM + Kragel response ensemble and target scoring."""
from __future__ import annotations

import math
from typing import Any

COMMON = ("happiness", "surprise", "fear", "sadness", "anger", "neutral", "contempt", "disgust")
TSAM_MAP = {
    "Anger": "anger", "Contempt": "contempt", "Disgust": "disgust", "Fear": "fear",
    "Happiness": "happiness", "Neutral": "neutral", "Sadness": "sadness", "Surprise": "surprise",
}
KRAGEL_MAP = {
    "amused": "happiness", "content": "happiness", "angry": "anger", "fearful": "fear",
    "neutral": "neutral", "sad": "sadness", "surprised": "surprise",
}
ENSEMBLE_PROFILE = "tsam55-kragel45-relative-evidence-v1"


def _softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    if not values:
        return []
    peak = max(values)
    exps = [math.exp((v-peak)/temperature) for v in values]
    total = sum(exps)
    return [v/total for v in exps]


def tsam_relative(result: dict | None) -> dict[str, float] | None:
    if not result or result.get("status") != "experimental" or not result.get("windows"):
        return None
    labels = result.get("labels") or []
    rows = []
    for window in result["windows"]:
        logits = [float(v) for v in window.get("logits", [])]
        if len(logits) != len(labels):
            continue
        probs = _softmax(logits)
        rows.append({TSAM_MAP.get(label, label.lower()): probs[i] for i, label in enumerate(labels)})
    if not rows:
        return None
    return {name: sum(row.get(name, 0.0) for row in rows)/len(rows) for name in COMMON}


def kragel_relative(result: dict | None) -> dict[str, float] | None:
    if not result or result.get("status") != "experimental" or not result.get("aggregate"):
        return None
    aggregate = result["aggregate"]
    labels = list(aggregate)
    probs = _softmax([float(aggregate[x]) for x in labels], temperature=0.12)
    out = {name: 0.0 for name in COMMON}
    contributions: dict[str, list[float]] = {}
    for label, value in zip(labels, probs):
        mapped = KRAGEL_MAP.get(label)
        if mapped:
            contributions.setdefault(mapped, []).append(value)
    for name, values in contributions.items():
        out[name] = sum(values)
    # Kragel has no contempt/disgust signatures. Keep them absent from its weight,
    # rather than treating absence as evidence of zero emotion.
    return out


def ensemble(evidence: dict[str, Any]) -> dict:
    tsam = tsam_relative(evidence.get("tsam"))
    kragel = kragel_relative(evidence.get("kragel"))
    weights = {"tsam": 0.55 if tsam else 0.0, "kragel": 0.45 if kragel else 0.0}
    values: dict[str, float | None] = {}
    disagreement: dict[str, float] = {}
    for emotion in COMMON:
        parts = []
        if tsam is not None:
            parts.append((weights["tsam"], tsam.get(emotion, 0.0)))
        # Kragel does not define contempt/disgust.
        if kragel is not None and emotion not in {"contempt", "disgust"}:
            parts.append((weights["kragel"], kragel.get(emotion, 0.0)))
        total = sum(weight for weight, _ in parts)
        values[emotion] = sum(weight*value for weight, value in parts)/total if total else None
        if tsam is not None and kragel is not None and emotion not in {"contempt", "disgust"}:
            disagreement[emotion] = abs(tsam.get(emotion, 0.0)-kragel.get(emotion, 0.0))
    mean_disagreement = sum(disagreement.values())/len(disagreement) if disagreement else None
    active = [name for name, weight in weights.items() if weight]
    return {
        "profile": ENSEMBLE_PROFILE,
        "values": values,
        "sources": {"tsam": tsam, "kragel": kragel},
        "source_weights": weights,
        "active_sources": active,
        "disagreement": disagreement,
        "mean_disagreement": mean_disagreement,
        "confidence": "moderate" if len(active) == 2 and (mean_disagreement or 0) < 0.25 else "low",
        "interpretation": "Relative model evidence combined transparently across available TSAM and Kragel sources; not calibrated human emotion probabilities.",
    }


def target_score(report: dict, target: dict | None) -> dict | None:
    if not target or not target.get("emotions"):
        return None
    requested = target["emotions"]
    values = report["values"]
    weighted_error = 0.0
    weight_total = 0.0
    dimensions = []
    for emotion, specification in requested.items():
        actual = values.get(emotion)
        if actual is None:
            continue
        desired = float(specification.get("desired", 0.5))
        weight = float(specification.get("weight", 1.0))
        error = abs(actual-desired)
        weighted_error += weight*error
        weight_total += weight
        dimensions.append({"emotion": emotion, "desired": desired, "actual": actual, "weight": weight, "error": error})
    if weight_total == 0:
        return None
    match = max(0.0, 1.0-weighted_error/weight_total)
    disagreement = report.get("mean_disagreement")
    penalty = min(0.15, float(disagreement or 0)*0.2)
    final = max(0.0, match-penalty)
    return {
        "metric": "response-target-distance/v1",
        "value": final,
        "raw_match": match,
        "disagreement_penalty": penalty,
        "dimensions": dimensions,
        "scale": [0, 1],
        "interpretation": "Closeness of relative TSAM/Kragel model evidence to the declared target. This is an optimization score, not a measured human response rate.",
    }
