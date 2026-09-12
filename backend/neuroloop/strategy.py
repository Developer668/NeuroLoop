"""Deterministic typed intervention proposals for the bounded creative loop."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StrategyFamily = Literal["visual", "temporal", "copy", "narrative", "audio", "generative"]
SUPPORTED_OPERATORS = (
    "contrast_up", "contrast_down", "brightness_up", "brightness_down",
    "saturation_up", "saturation_down", "headline_early", "headline_late",
)
FILTER_OPERATORS = frozenset(SUPPORTED_OPERATORS[:6])
BACKEND_IDENTITY = "creative-strategist/deterministic-v1"
PROPOSAL_VERSION = "intervention-proposal/v1"
EMOTIONS = frozenset(("happiness", "surprise", "fear", "sadness", "anger", "neutral", "contempt", "disgust"))


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True, populate_by_name=True)


class NormalizedWindow(_Model):
    start: float = Field(ge=0, le=1)
    end: float = Field(gt=0, le=1)
    id: str = Field(default="whole-creative", min_length=1, max_length=120)
    label: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def ordered(self) -> "NormalizedWindow":
        if not math.isfinite(self.start) or not math.isfinite(self.end) or self.end <= self.start:
            raise ValueError("Normalized window must satisfy finite 0 <= start < end <= 1")
        return self


class ResponseGap(_Model):
    dimension: str = Field(min_length=1, max_length=80)
    desired: float | None = Field(default=None, ge=0, le=1)
    actual: float | None = Field(default=None, ge=0, le=1)
    delta: float | None = None
    direction: Literal["increase", "decrease", "maintain", "unknown"] = "unknown"
    weight: float = Field(default=1, gt=0, le=5)
    coverage: float = Field(default=1, ge=0, le=1)
    window: NormalizedWindow

    @field_validator("delta")
    @classmethod
    def finite_delta(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Response gap must be finite")
        return value


class RequestedChange(_Model):
    type: Literal["ffmpeg_filter", "composition_timing", "copy", "narrative", "audio", "generative"]
    operator: str = Field(min_length=1, max_length=80)
    parameter: str = Field(min_length=1, max_length=120)
    value: str | float | int | None = None
    exact: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def supported(self) -> "RequestedChange":
        if self.operator not in SUPPORTED_OPERATORS:
            raise ValueError("Requested change contains an unsupported operator")
        return self


class ExpectedRelativeEvidenceEffect(_Model):
    metric: str = Field(default="response-target-distance/v1", min_length=1, max_length=160)
    direction: Literal["improve_toward_target", "increase", "decrease", "maintain", "unknown"]
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    magnitude: Literal["bounded", "small", "unknown"] = "bounded"
    evidence_only: bool = True
    note: str = Field(default="Expected relative model-evidence change only; not a human response claim.", max_length=300)


class ProposalProvenance(_Model):
    contract: Literal["intervention-proposal/v1"] = PROPOSAL_VERSION
    backend_identity: str = Field(default=BACKEND_IDENTITY, min_length=1, max_length=160)
    target_digest: str = Field(min_length=16, max_length=128)
    response_profile: str | None = Field(default=None, max_length=200)
    timeline_digest: str = Field(min_length=16, max_length=128)
    constraints_digest: str = Field(min_length=16, max_length=128)
    reasoning: str = Field(default="deterministic gap-to-operator mapping", max_length=300)


class InterventionProposal(_Model):
    """Reviewable request with no executable command or human-response claim."""

    version: Literal["intervention-proposal/v1"] = PROPOSAL_VERSION
    candidate_id: str | None = Field(default=None, max_length=120)
    lineage_id: str = Field(default="", max_length=160)
    parent_experiment_id: str | None = Field(default=None, max_length=120)
    branch: Literal["A", "B", "C"] = "A"
    operator: str = Field(min_length=1, max_length=80)
    targeted_window: NormalizedWindow
    response_gap: ResponseGap
    strategy_family: StrategyFamily
    hypothesis: str = Field(min_length=1, max_length=1000)
    requested_changes: list[RequestedChange] = Field(min_length=1, max_length=4)
    expected_relative_evidence_effect: ExpectedRelativeEvidenceEffect
    preserve: list[str] = Field(min_length=1, max_length=16)
    confidence: float = Field(ge=0, le=1)
    provenance: ProposalProvenance
    backend_identity: str = Field(default=BACKEND_IDENTITY, min_length=1, max_length=160)

    @field_validator("confidence")
    @classmethod
    def finite_confidence(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Proposal confidence must be finite")
        return value

    @model_validator(mode="after")
    def contract(self) -> "InterventionProposal":
        if self.operator not in SUPPORTED_OPERATORS:
            raise ValueError("Proposal contains an unsupported operator")
        if self.backend_identity != self.provenance.backend_identity:
            raise ValueError("Proposal and provenance backend identities must match")
        if any(change.operator != self.operator for change in self.requested_changes):
            raise ValueError("Requested changes must use the proposal operator")
        return self

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


@dataclass(frozen=True)
class OperatorImplementation:
    operator: str
    strategy_family: StrategyFamily
    renderer: Literal["ffmpeg_filter", "composition_timing"]
    parameter: str
    value: float
    delta_seconds: float | None
    filter_expression: str | None
    exact_change: str


_FILTER_EXPRESSIONS = {
    "contrast_up": "eq=contrast=1.08", "contrast_down": "eq=contrast=0.92",
    "brightness_up": "eq=brightness=0.035", "brightness_down": "eq=brightness=-0.035",
    "saturation_up": "eq=saturation=1.12", "saturation_down": "eq=saturation=0.88",
}
_FILTER_VALUES = {
    "contrast_up": 1.08, "contrast_down": 0.92, "brightness_up": 0.035,
    "brightness_down": -0.035, "saturation_up": 1.12, "saturation_down": 0.88,
}


def operator_implementation(operator: str) -> OperatorImplementation:
    """Describe one of the existing bounded FFmpeg/composition operators."""

    if operator in FILTER_OPERATORS:
        expression = _FILTER_EXPRESSIONS[operator]
        return OperatorImplementation(operator, "visual", "ffmpeg_filter", operator.rsplit("_", 1)[0], _FILTER_VALUES[operator], None, expression, f"Apply the existing bounded FFmpeg filter {expression} once.")
    if operator in {"headline_early", "headline_late"}:
        delta = -0.75 if operator == "headline_early" else 0.75
        return OperatorImplementation(operator, "temporal", "composition_timing", "headline_start", delta, delta, None, f"Move the editable headline start by {delta:+.2f} seconds, clamped to the duration.")
    raise ValueError("Unsupported controlled operator")


def _map(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump(mode="json")
        return dict(result) if isinstance(result, Mapping) else {}
    return {}


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()


def _windows(target_spec: Any) -> list[dict[str, Any]]:
    target, emotions = _map(target_spec), _map(target_spec).get("emotions") or {}
    rows, explicit = target.get("windows") or target.get("time_windows") or target.get("segments"), target.get("time_window") or target.get("window")
    if rows and explicit:
        raise ValueError("Target cannot specify both one time_window and windows")
    if rows:
        if not isinstance(rows, list):
            raise ValueError("Target windows must be a list")
        return [{"id": str(_map(row).get("id") or _map(row).get("window_id") or f"window-{i + 1}"), "label": str(_map(row).get("label") or ""), "start": _number(_map(row).get("start"), "target window start"), "end": _number(_map(row).get("end"), "target window end"), "emotions": _map(row).get("emotions") or emotions} for i, row in enumerate(rows)]
    if explicit:
        row = _map(explicit)
        return [{"id": str(row.get("id") or "time-window"), "label": str(row.get("label") or ""), "start": _number(row.get("start"), "target time_window start"), "end": _number(row.get("end"), "target time_window end"), "emotions": emotions}]
    return [{"id": "whole-creative", "label": "", "start": 0.0, "end": 1.0, "emotions": emotions}]


def _overlap(row: Mapping[str, Any], start: float, end: float) -> float:
    left, right = row.get("start_norm"), row.get("end_norm")
    if left is None or right is None:
        interval = row.get("window")
        if isinstance(interval, (list, tuple)) and len(interval) == 2:
            left, right = interval
        else:
            return 0
    try:
        return max(0.0, min(end, _number(right, "response interval end")) - max(start, _number(left, "response interval start")))
    except ValueError:
        return 0


def _average(rows: Any, start: float, end: float) -> tuple[dict[str, float], float]:
    if not isinstance(rows, list):
        return {}, 0
    totals: dict[str, float] = {}
    widths: dict[str, float] = {}
    covered = 0.0
    for raw in rows:
        row, width = _map(raw), 0.0
        width = _overlap(row, start, end)
        if width <= 0:
            continue
        covered = min(end - start, covered + width)
        values = row.get("values")
        if not isinstance(values, Mapping):
            continue
        for name, value in values.items():
            if name not in EMOTIONS or value is None:
                continue
            try:
                number = _number(value, f"response value {name}")
            except ValueError:
                continue
            totals[name] = totals.get(name, 0) + width * number
            widths[name] = widths.get(name, 0) + width
    return {name: totals[name] / widths[name] for name in totals if widths[name]}, min(1.0, covered / (end - start)) if end > start else 0


def _values(report: Any, window: NormalizedWindow) -> tuple[dict[str, float], float]:
    response = _map(report)
    if window.start == 0 and window.end == 1 and isinstance(response.get("values"), Mapping):
        return dict(response["values"]), 1.0
    source_series, totals, weights, coverage = response.get("source_series"), {}, {}, 0.0
    if isinstance(source_series, Mapping):
        source_weights = response.get("source_weights") or {"tsam": 0.55, "kragel": 0.45}
        for source in ("tsam", "kragel"):
            values, source_coverage = _average(source_series.get(source), window.start, window.end)
            weight = max(0.0, float(source_weights.get(source, 0))) * source_coverage
            if not values or weight <= 0:
                continue
            coverage = max(coverage, source_coverage)
            for name, value in values.items():
                totals[name] = totals.get(name, 0) + weight * value
                weights[name] = weights.get(name, 0) + weight
        if weights:
            return {name: totals[name] / weights[name] for name in totals}, coverage
    return _average(response.get("series"), window.start, window.end)


def _target_value(value: Any) -> tuple[float, float]:
    spec = _map(value)
    desired = _number(spec.get("desired", 0.5), "target desired value") if spec else _number(value, "target desired value")
    weight = _number(spec.get("weight", 1), "target weight") if spec else 1.0
    if not 0 <= desired <= 1 or weight <= 0:
        raise ValueError("Target desired value/weight is outside its bounds")
    return desired, weight


def _gap(target_spec: Any, report: Any) -> tuple[NormalizedWindow, ResponseGap]:
    candidates: list[tuple[float, int, ResponseGap]] = []
    for index, raw in enumerate(_windows(target_spec)):
        window = NormalizedWindow(id=raw["id"], label=raw["label"], start=raw["start"], end=raw["end"])
        values, coverage = _values(report, window)
        emotions = raw.get("emotions") or {}
        if not isinstance(emotions, Mapping):
            raise ValueError("Target emotions must be an object")
        for dimension, raw_target in emotions.items():
            if dimension not in EMOTIONS:
                raise ValueError(f"Target contains unsupported dimension {dimension!r}")
            desired, weight = _target_value(raw_target)
            actual = values.get(dimension)
            if actual is not None:
                actual = _number(actual, f"response value {dimension}")
                if not 0 <= actual <= 1:
                    raise ValueError(f"Response value {dimension} must be between zero and one")
                delta = desired - actual
                direction = "increase" if delta > 1e-9 else "decrease" if delta < -1e-9 else "maintain"
                magnitude = abs(delta) * weight * max(coverage, 0.01)
            else:
                delta, direction, magnitude = None, "unknown", weight * 0.01
            candidates.append((magnitude, -index, ResponseGap(dimension=dimension, desired=desired, actual=actual, delta=delta, direction=direction, weight=weight, coverage=coverage, window=window)))
    if candidates:
        gap = max(candidates, key=lambda item: (item[0], item[1], item[2].dimension))[2]
        return gap.window, gap
    window = NormalizedWindow(start=0, end=1)
    return window, ResponseGap(dimension="evidence", coverage=0, window=window)


def _prior(prior_experiments: Iterable[Any]) -> list[dict[str, Any]]:
    result = []
    for item in prior_experiments or ():
        result.append(dict(item) if isinstance(item, Mapping) else {key: getattr(item, key) for key in ("operator", "decision", "asset_id") if hasattr(item, key)})
    return result


def _rank(gap: ResponseGap, timeline: Any, prior: Sequence[Mapping[str, Any]], constraints: Mapping[str, Any], allowed: Sequence[str]) -> list[str]:
    attempted = {str(row.get("operator")) for row in prior if row.get("operator") and row.get("decision") != "proposed"}
    options = [item for item in dict.fromkeys(allowed) if item in SUPPORTED_OPERATORS and item not in attempted]
    cap, kept_filters = constraints.get("max_filter_edits", 2), sum(row.get("decision") == "kept" and row.get("operator") in FILTER_OPERATORS for row in prior)
    if isinstance(cap, int) and kept_filters >= cap:
        options = [item for item in options if item not in FILTER_OPERATORS]
    if gap.direction == "increase":
        preferred = ["saturation_up", "contrast_up", "brightness_up", "headline_early", "headline_late"]
    elif gap.direction == "decrease":
        preferred = ["saturation_down", "contrast_down", "brightness_down", "headline_late", "headline_early"]
    else:
        preferred = ["contrast_up", "brightness_up", "saturation_up", "headline_early", "headline_late"]
    info = _map(timeline)
    has_headline = info.get("headline_start") is not None or info.get("has_headline") is True or _map(info.get("composition")).get("headline_start") is not None
    if has_headline and gap.window.end - gap.window.start < 0.5:
        headline = "headline_early" if gap.window.start < 0.5 else "headline_late"
        preferred = [headline] + [item for item in preferred if item != headline]
    order = {item: i for i, item in enumerate(preferred)}
    return sorted(options, key=lambda item: (order.get(item, len(preferred)), options.index(item)))


class CreativeStrategist:
    """Small deterministic gap-to-operator mapper; no external reasoning backend."""

    backend_identity = BACKEND_IDENTITY

    def propose(self, target_spec: Any, response_report: Any, timeline: Any, prior_experiments: Iterable[Any], constraints: Mapping[str, Any] | None, *, allowed_operators: Sequence[str] = SUPPORTED_OPERATORS, seed: str = "", lineage_id: str | None = None, parent_experiment_id: str | None = None) -> InterventionProposal | None:
        candidates = self.propose_candidates(target_spec, response_report, timeline, prior_experiments, constraints, allowed_operators=allowed_operators, max_candidates=1, seed=seed, lineage_id=lineage_id, parent_experiment_id=parent_experiment_id)
        return candidates[0] if candidates else None

    def propose_candidates(self, target_spec: Any, response_report: Any, timeline: Any, prior_experiments: Iterable[Any], constraints: Mapping[str, Any] | None, *, allowed_operators: Sequence[str] = SUPPORTED_OPERATORS, max_candidates: int = 3, seed: str = "", lineage_id: str | None = None, parent_experiment_id: str | None = None) -> list[InterventionProposal]:
        if max_candidates < 1:
            return []
        max_candidates, locked, rows = min(3, int(max_candidates)), dict(constraints or {}), _prior(prior_experiments)
        window, gap = _gap(target_spec, response_report)
        options = _rank(gap, timeline, rows, locked, allowed_operators)[:max_candidates]
        if not options:
            return []
        response, target = _map(response_report), _map(target_spec)
        lineage = lineage_id or "lineage-" + _digest({"target": target, "response": response, "timeline": timeline, "constraints": locked, "seed": seed})[:32]
        preserve = ["duration", "source_asset", "evaluator_profile", "model_weights"]
        if locked.get("preserve_audio", True):
            preserve.insert(2, "audio")
        if locked.get("locked_copy"):
            preserve.insert(2, "exact_copy")
        provenance = {"backend_identity": self.backend_identity, "target_digest": _digest(target), "response_profile": response.get("profile"), "timeline_digest": _digest(timeline), "constraints_digest": _digest(locked)}
        proposals = []
        for index, operator in enumerate(options):
            implementation = operator_implementation(operator)
            change = RequestedChange(type=implementation.renderer, operator=operator, parameter=implementation.parameter, value=implementation.value, exact=implementation.exact_change)
            proposals.append(InterventionProposal(candidate_id=f"{lineage}:{chr(65 + index)}", lineage_id=lineage, parent_experiment_id=parent_experiment_id, branch=chr(65 + index), operator=operator, targeted_window=window, response_gap=gap, strategy_family=implementation.strategy_family, hypothesis=f"Test {implementation.exact_change.lower()} in normalized window [{window.start:.3f}, {window.end:.3f}] to address the {gap.dimension} evidence gap; evaluate with the fixed relative metric and make no human-response claim.", requested_changes=[change], expected_relative_evidence_effect=ExpectedRelativeEvidenceEffect(metric=str(response.get("metric") or "response-target-distance/v1"), direction="improve_toward_target" if gap.desired is not None else "unknown", dimensions=[gap.dimension] if gap.dimension in EMOTIONS else []), preserve=preserve, confidence=max(0.0, (0.65 if gap.actual is not None and gap.coverage else 0.35) - index * 0.03), provenance=ProposalProvenance(**provenance), backend_identity=self.backend_identity))
        return proposals

    propose_many = propose_candidates


def propose_interventions(target_spec: Any, response_report: Any, timeline: Any, prior_experiments: Iterable[Any], constraints: Mapping[str, Any] | None, *, allowed_operators: Sequence[str] = SUPPORTED_OPERATORS, max_candidates: int = 3, seed: str = "", lineage_id: str | None = None, parent_experiment_id: str | None = None) -> list[InterventionProposal]:
    return CreativeStrategist().propose_candidates(target_spec, response_report, timeline, prior_experiments, constraints, allowed_operators=allowed_operators, max_candidates=max_candidates, seed=seed, lineage_id=lineage_id, parent_experiment_id=parent_experiment_id)
