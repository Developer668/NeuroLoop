"""Context-scoped Thompson sampling for bounded model-evidence experiments."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from .db import PolicyStat, Session, now


OPERATORS = {
    "contrast_up": ("Increase contrast by 8%", "A bounded contrast increase may move the fixed model-evidence score toward the target."),
    "contrast_down": ("Reduce contrast by 8%", "A bounded contrast reduction may move the fixed model-evidence score toward the target."),
    "brightness_up": ("Increase brightness by 0.035", "Test a small luminance change while preserving timing and assets."),
    "brightness_down": ("Reduce brightness by 0.035", "Test a small luminance change while preserving timing and assets."),
    "saturation_up": ("Increase saturation by 12%", "Test a bounded color-intensity change; this is not a claim about emotion."),
    "saturation_down": ("Reduce saturation by 12%", "Test a bounded color-intensity change; this is not a claim about emotion."),
    "headline_early": ("Move headline 0.75 seconds earlier", "Test headline timing while preserving the exact copy and source image."),
    "headline_late": ("Move headline 0.75 seconds later", "Test headline timing while preserving the exact copy and source image."),
}
VALID_OUTCOME_DECISIONS = frozenset({"kept", "reverted", "tradeoff"})
MAX_BRANCHES = 3


@dataclass(frozen=True)
class PolicyOutcome:
    context: str
    operator: str
    gain: float
    seconds: float
    threshold: float
    decision: str
    valid: bool = True


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    dump = getattr(value, "model_dump", None)
    return _jsonable(dump(mode="json")) if callable(dump) else value


def context_id(value: Any = None, **parts: Any) -> str:
    """Hash the fixed target/evaluator/timeline/constraint context."""

    payload = _jsonable(parts if parts else value)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:32]


def _choices(context: str, allowed: Sequence[str], excluded: set[str], seed: str) -> list[dict[str, Any]]:
    names = [name for name in allowed if name in OPERATORS and name not in excluded]
    if not names:
        return []
    rng, choices = random.Random(seed), []
    with Session() as db:
        for name in names:
            row = db.get(PolicyStat, f"{context}:{name}")
            successes, failures = (row.successes, row.failures) if row else (0, 0)
            sample = rng.betavariate(1 + successes, 1 + failures)
            cost = row.total_seconds / (successes + failures) if row and successes + failures else 30.0
            choices.append({"operator": name, "sampled_useful_edit_rate": sample, "selection_utility": sample / max(cost, 1.0), "attempts": successes + failures, "successes": successes, "failures": failures})
    return choices


def choose(context: str, allowed: list[str], excluded: set[str], seed: str) -> dict | None:
    """Choose one permitted operator reproducibly within ``context``."""

    choices = _choices(context, allowed, excluded, seed)
    if not choices:
        return None
    selected = max(choices, key=lambda item: item["selection_utility"])
    return {**selected, "hypothesis": OPERATORS[selected["operator"]][1], "label": OPERATORS[selected["operator"]][0], "source": "context-scoped cost-aware Thompson sampling", "candidates": choices}


def choose_batch(context: str, allowed: Sequence[str], excluded: set[str] | None, seed: str, *, limit: int = MAX_BRANCHES) -> list[dict[str, Any]]:
    """Choose at most three distinct operators for one sibling lineage."""

    used, selected = set(excluded or ()), []
    for index in range(min(MAX_BRANCHES, max(0, int(limit)))):
        choice = choose(context, list(allowed), used, f"{seed}:branch:{index}")
        if choice is None:
            break
        selected.append(choice)
        used.add(choice["operator"])
    return selected


def _numbers(gain: Any, seconds: Any, threshold: Any) -> tuple[float, float, float] | None:
    try:
        values = (float(gain), float(seconds), float(threshold))
    except (TypeError, ValueError):
        return None
    return values if all(math.isfinite(value) for value in values) and values[1] >= 0 and values[2] > 0 else None


def _write(db: Any, context: str, operator: str, gain: float, seconds: float, success: bool) -> None:
    key, row = f"{context}:{operator}", db.get(PolicyStat, f"{context}:{operator}")
    if row is None:
        row = PolicyStat(key=key, context=context, operator=operator, successes=0, failures=0, total_gain=0, total_seconds=0)
        db.add(row)
    if success:
        row.successes += 1
    else:
        row.failures += 1
    row.total_gain += gain
    row.total_seconds += seconds
    row.updated_at = now()


def record_outcome_in_session(db: Any, outcome: PolicyOutcome) -> bool:
    """Update policy statistics only for a finite, scoreable candidate."""

    values = _numbers(outcome.gain, outcome.seconds, outcome.threshold)
    if not outcome.valid or not outcome.context or outcome.operator not in OPERATORS or outcome.decision not in VALID_OUTCOME_DECISIONS or values is None:
        return False
    gain, seconds, threshold = values
    _write(db, outcome.context, outcome.operator, gain, seconds, outcome.decision != "tradeoff" and gain >= threshold)
    return True


def record_valid_in_session(db: Any, context: str, operator: str, gain: float, seconds: float, threshold: float, *, decision: str, valid: bool = True) -> bool:
    return record_outcome_in_session(db, PolicyOutcome(context, operator, gain, seconds, threshold, decision, valid))


def record_outcome(context: str, operator: str, gain: float, seconds: float, threshold: float, *, decision: str = "reverted", valid: bool = True) -> bool:
    with Session.begin() as db:
        return record_valid_in_session(db, context, operator, gain, seconds, threshold, decision=decision, valid=valid)


def update(context: str, operator: str, gain: float, seconds: float, threshold: float, *, decision: str = "reverted", valid: bool = True) -> bool:
    return record_outcome(context, operator, gain, seconds, threshold, decision=decision, valid=valid)


choose_candidates = choose_batch
record_valid = record_outcome


def record_in_session(db: Any, context: str, operator: str, gain: float, seconds: float, threshold: float) -> None:
    values = _numbers(gain, seconds, threshold)
    if not context or operator not in OPERATORS or values is None:
        return
    gain_value, seconds_value, threshold_value = values
    _write(db, context, operator, gain_value, seconds_value, gain_value >= threshold_value)


def record(context: str, operator: str, gain: float, seconds: float, threshold: float) -> None:
    with Session.begin() as db:
        record_in_session(db, context, operator, gain, seconds, threshold)


def history() -> list[dict]:
    with Session() as db:
        return [{"context": row.context, "operator": row.operator, "successes": row.successes, "failures": row.failures, "attempts": row.successes + row.failures, "mean_gain": row.total_gain / max(1, row.successes + row.failures), "mean_seconds": row.total_seconds / max(1, row.successes + row.failures), "updated_at": row.updated_at} for row in db.scalars(select(PolicyStat).order_by(PolicyStat.updated_at.desc())).all()]
