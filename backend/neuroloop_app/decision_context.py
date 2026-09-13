"""Provider-only projection; the engine's complete evidence receipt is unchanged."""
from __future__ import annotations

from copy import deepcopy
import re

from .domain import digest


PROJECTION_VERSION = "decision-context/v1"

# Numeric diagnostics are not selection evidence when their own producer marks
# them ineligible. Everything else, including unknown warnings, is retained.
_DIAGNOSTIC_FIELDS = frozenset({
    "times", "segment_durations", "time_axis", "trajectories", "aggregate",
    "top_pattern", "ribbon_depths", "coverage", "values", "diagnostic_sources",
    "source_series", "series", "excluded_padding_rows",
})


def _numbers_only(value) -> bool:
    if isinstance(value, dict):
        return all(_numbers_only(v) for v in value.values())
    if isinstance(value, list):
        return all(_numbers_only(v) for v in value)
    return value is None or isinstance(value, (int, float)) and not isinstance(value, bool)


def _provenance_metadata(value, path="") -> dict:
    """Keep every textual caveat and status, excluding bulky checksum inventories."""
    if isinstance(value, dict):
        kept = {}
        for key, child in value.items():
            kept.update(_provenance_metadata(child, f"{path}/{key}"))
        return kept
    if isinstance(value, list):
        kept = {}
        for index, child in enumerate(value):
            kept.update(_provenance_metadata(child, f"{path}/{index}"))
        return kept
    if isinstance(value, str) and not re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
        return {path: value}
    if value is None or isinstance(value, bool):
        return {path: value}
    return {}


def _excluded_projection(value: dict) -> dict:
    omitted = {k: v for k, v in value.items() if k in _DIAGNOSTIC_FIELDS and _numbers_only(v)}
    kept = {k: deepcopy(v) for k, v in value.items() if k not in omitted}
    provenance = value.get("provenance")
    if isinstance(provenance, dict):
        kept["provenance"] = {
            "original_sha256": digest(provenance),
            "model": deepcopy(provenance.get("model")),
            "checkpoint": deepcopy(provenance.get("checkpoint")),
            "metadata": _provenance_metadata(provenance),
            "projection_note": "Numerical geometry and checksum inventories remain in the original stored provenance. Every textual caveat and boolean status is retained below by original path.",
        }
    if omitted:
        kept["diagnostic_projection"] = {
            "version": PROJECTION_VERSION,
            "original_sha256": digest(value),
            "omitted_fields": sorted(omitted),
            "meaning": "Decision-ineligible numerical diagnostics omitted from the provider context only; the complete original receipt remains stored. Omission is not missing execution or a zero score.",
        }
    return kept


def project_decision_context(state: dict) -> dict:
    """Copy decision state, pruning only explicitly excluded optional diagnostics.

    Full scores, constraints, evaluation provenance and warnings survive verbatim. Unknown
    schemas and absent eligibility flags are deliberately not inferred as false.
    """
    projected = deepcopy(state)
    optional = set(state.get("config", {}).get("optional_evaluators", []))
    required = set(state.get("config", {}).get("required_evaluators", []))
    for bundle in projected.get("evidence_bundles", []):
        for evaluation in bundle.get("evaluations", []):
            evaluator = evaluation.get("evaluator")
            result = evaluation.get("result", {})
            if evaluator not in optional or evaluator in required or result.get("scores") != {}:
                continue
            observations = result.get("observations")
            if not isinstance(observations, dict):
                continue
            original_hash = digest(observations)
            changed = False
            # These named public contracts have independent eligibility. A
            # Kragel exclusion must never exclude the parent TRIBE evaluation.
            for name in ("kragel", "response_ensemble"):
                value = observations.get(name)
                if isinstance(value, dict) and value.get("decision_eligible") is False:
                    compact = _excluded_projection(value)
                    changed = changed or compact != value
                    observations[name] = compact
            if changed:
                observations["decision_context_projection"] = {
                    "version": PROJECTION_VERSION,
                    "original_observations_sha256": original_hash,
                    "evaluation_id": evaluation.get("id"),
                }
    return projected
