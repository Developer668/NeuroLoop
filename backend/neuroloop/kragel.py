"""Experimental Kragel 2015 pattern expression on TRIBE fsaverage5 output.

Published Kragel signatures are MNI-space volumes.  This adapter samples each
volume through the documented fsaverage5 white-to-pial ribbon using the
volume's inverse affine, five evenly spaced ribbon depths, and left-then-right
hemisphere order matching the 20,484-value TRIBE head.  It does not index-
resample the published high-resolution surface files.

Outputs are TRIBE-derived model evidence, not calibrated probabilities or
observed human emotions.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from .config import settings
from .readout import validate_response
from .response import PROVENANCE_VERSION, TIME_AXIS_VERSION, normalized_axis

EMOTIONS = ("amused", "angry", "content", "fearful", "neutral", "sad", "surprised")
HEMISPHERES = ("left", "right")
TRIBE_VERTICES_PER_HEMISPHERE = 10242
RIBBON_DEPTHS = (0.0, 0.25, 0.5, 0.75, 1.0)
PROFILE = "kragel2015-bpls-mni-volume-to-fsaverage5-ribbon-v1"
CODE_VERSION = "kragel-registration-contract-v3"
PROJECTION_VERSION = "explicit-surface-to-volume-ribbon-v3"
GEOMETRY_VERSION = "fsaverage5-gifti-left-right-v1"


def _source() -> Path:
    return settings().root / "models/brain_readouts/kragel2015/source"


def _geometry(name: str) -> Path:
    return settings().data / "geometry" / name


def _volume_path(emotion: str) -> Path:
    matches = sorted(_source().glob(f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.hdr"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Kragel {emotion} volume is missing")
    return matches[0]


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registration() -> dict:
    """Report registration separately from downloaded assets and interpolation.

    No filename or successful projection establishes spatial registration.
    An optional externally reviewed registration can supply the complete chain.
    The receipt is bound to the exact four surfaces and fourteen volume files.
    """
    path = _geometry("kragel-registration.json")
    base = {
        "version": "kragel-registration-receipt-v1",
        "verified": False,
        "decision_eligible": False,
        "status": "unverified_coordinate_assumption",
        "surface_space": "fsaverage5 surface RAS; GIFTI metadata alone does not establish MNI152",
        "volume_space": "published Kragel MNI volume; exact template registration requires review",
        "surface_to_volume_world": np.eye(4).tolist(),
        "reason": "Diagnostic projection assumes identical surface and volume world coordinates. The complete surface-RAS to volume-world registration has not been verified.",
        "reference": "https://surfer.nmr.mgh.harvard.edu/fswiki/CoordinateSystems",
    }
    if not path.is_file():
        return base
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        matrix = np.asarray(receipt["surface_to_volume_world"], dtype=float)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-10 or not np.allclose(matrix[3], [0, 0, 0, 1]):
            raise ValueError("Registration matrix must be a finite invertible homogeneous 4-by-4 affine")
        expected_geometry = _geometry_manifest()["files"]
        expected_volumes = {path.name: _sha256(path) for emotion in EMOTIONS for path in (_volume_path(emotion), _volume_path(emotion).with_suffix(".img"))}
        if receipt.get("geometry_sha256") != expected_geometry or receipt.get("volume_sha256") != expected_volumes:
            raise ValueError("Registration receipt does not match the current surface and signature files")
        for field in ("source_space", "target_space", "method", "reviewed_by", "reference"):
            if not isinstance(receipt.get(field), str) or not receipt[field].strip():
                raise ValueError(f"Registration receipt needs {field}")
        validation = receipt.get("validation", {})
        if validation.get("spatial_alignment_passed") is not True or validation.get("hemisphere_order_passed") is not True or not validation.get("report_sha256"):
            raise ValueError("Registration receipt requires spatial alignment, hemisphere-order checks and a report hash")
        return {**base, **receipt, "verified": True, "decision_eligible": False,
                "status": "reviewed_registration_transfer_unvalidated", "receipt_sha256": _sha256(path),
                "reason": "Spatial registration has an external review receipt; transfer to TRIBE and emotion decision validity remain unvalidated."}
    except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
        return {**base, "status": "invalid_registration_receipt", "reason": str(exc), "receipt_sha256": _sha256(path)}


def status() -> dict:
    required = [
        _source() / f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.{suffix}"
        for emotion in EMOTIONS for suffix in ("hdr", "img")
    ] + [_geometry(f"{kind}_{hemi}.gii.gz") for kind in ("pial", "white") for hemi in HEMISPHERES]
    missing = []
    for path in required:
        if not path.is_file():
            try:
                missing.append(str(path.relative_to(settings().root)))
            except ValueError:
                missing.append(str(path))
    return {
        "status": "experimental_ready" if not missing else "missing_assets",
        "profile": PROFILE,
        "registration": registration(),
        "decision_eligible": False,
        "missing": missing,
        "mesh": "fsaverage5",
        "hemisphere_order": list(HEMISPHERES),
        "vertices_per_hemisphere": TRIBE_VERTICES_PER_HEMISPHERE,
        "ribbon_depths": list(RIBBON_DEPTHS),
        "projection_version": PROJECTION_VERSION,
        "meaning": "Kragel 2015 BPLS pattern expression projected from published MNI volumes onto the TRIBE fsaverage5 cortical ribbon.",
    }


def _trilinear(data: np.ndarray, xyz_vox: np.ndarray) -> np.ndarray:
    """Finite-aware vectorized trilinear interpolation.

    Out-of-image locations and non-finite voxels are masked.  A vertex remains
    finite when at least one weighted corner is finite; weights are renormalized
    over the finite corners.  This prevents a single NaN in a volume from
    reaching a cortical score.
    """
    data = np.asarray(data, dtype=np.float64)
    points = np.asarray(xyz_vox, dtype=np.float64)
    if data.ndim != 3 or points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Trilinear sampling expects a 3-D volume and N-by-3 coordinates")
    shape = np.asarray(data.shape)
    lower = np.floor(points).astype(np.int64)
    fraction = points - lower
    valid = np.all(lower >= 0, axis=1) & np.all(lower + 1 < shape, axis=1) & np.isfinite(points).all(axis=1)
    output = np.full(len(points), np.nan, dtype=np.float64)
    if not np.any(valid):
        return output
    index = lower[valid]
    frac = fraction[valid]
    weights = []
    values = []
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                weight = (
                    (frac[:, 0] if dx else 1 - frac[:, 0])
                    * (frac[:, 1] if dy else 1 - frac[:, 1])
                    * (frac[:, 2] if dz else 1 - frac[:, 2])
                )
                values.append(data[index[:, 0] + dx, index[:, 1] + dy, index[:, 2] + dz])
                weights.append(weight)
    stacked_values = np.stack(values, axis=1)
    stacked_weights = np.stack(weights, axis=1)
    finite = np.isfinite(stacked_values)
    used_weights = np.where(finite, stacked_weights, 0.0)
    denominator = used_weights.sum(axis=1)
    numerator = np.where(finite, stacked_values, 0.0) * used_weights
    sampled = np.divide(numerator.sum(axis=1), denominator, out=np.full(len(denominator), np.nan), where=denominator > 0)
    output[np.flatnonzero(valid)] = sampled
    return output


def _coords(path: Path) -> np.ndarray:
    import nibabel as nib
    image = nib.load(str(path))
    arrays = [np.asarray(item.data, dtype=np.float64) for item in image.darrays if item.intent == 1008]
    if len(arrays) != 1 or arrays[0].shape != (TRIBE_VERTICES_PER_HEMISPHERE, 3):
        raise ValueError(f"Unexpected fsaverage5 geometry in {path.name}")
    if not np.isfinite(arrays[0]).all():
        raise ValueError(f"Non-finite fsaverage5 geometry in {path.name}")
    return arrays[0]


def _sample_volume(volume_path: Path) -> tuple[np.ndarray, float]:
    import nibabel as nib
    image = nib.load(str(volume_path))
    data = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float64)
    affine = np.asarray(image.affine, dtype=np.float64)
    if data.ndim != 3 or not np.isfinite(affine).all() or abs(float(np.linalg.det(affine))) < 1e-12:
        raise ValueError(f"Invalid Kragel volume or affine {volume_path.name}")
    inverse = np.linalg.inv(affine)
    registration_state = registration()
    if registration_state["status"] == "invalid_registration_receipt":
        raise ValueError(registration_state["reason"])
    transform = np.asarray(registration_state["surface_to_volume_world"], dtype=np.float64)
    hemispheres = []
    coverages = []
    for hemisphere in HEMISPHERES:
        pial = _coords(_geometry(f"pial_{hemisphere}.gii.gz"))
        white = _coords(_geometry(f"white_{hemisphere}.gii.gz"))
        samples = []
        for depth in RIBBON_DEPTHS:
            world = white * (1.0 - depth) + pial * depth
            vox = (inverse @ transform @ np.c_[world, np.ones(len(world))].T).T[:, :3]
            samples.append(_trilinear(data, vox))
        stacked = np.stack(samples)
        valid = np.isfinite(stacked)
        count = valid.sum(axis=0)
        values = np.divide(np.nansum(stacked, axis=0), count, out=np.full(TRIBE_VERTICES_PER_HEMISPHERE, np.nan), where=count > 0)
        coverages.append(float(np.isfinite(values).mean()))
        hemispheres.append(values)
    return np.concatenate(hemispheres), float(np.mean(coverages))


def _geometry_manifest() -> dict:
    files = {
        f"{kind}_{hemisphere}.gii.gz": _sha256(_geometry(f"{kind}_{hemisphere}.gii.gz"))
        for kind in ("pial", "white") for hemisphere in HEMISPHERES
    }
    return {
        "version": GEOMETRY_VERSION, "mesh": "fsaverage5", "hemisphere_order": list(HEMISPHERES),
        "vertices_per_hemisphere": TRIBE_VERTICES_PER_HEMISPHERE, "files": files,
        "sha256": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def _volume_manifest() -> dict:
    volumes = {}
    for emotion in EMOTIONS:
        path = _source() / f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.hdr"
        image_path = path.with_suffix('.img')
        item: dict[str, Any] = {"hdr_sha256": _sha256(path), "img_sha256": _sha256(image_path)}
        if path.is_file() and image_path.is_file():
            try:
                item["affine"] = _volume_affine_manifest(path)
            except Exception:
                item["affine"] = None
        else:
            item["affine"] = None
        volumes[emotion] = item
    return {"signature_version": "kragel-2015-bpls-v1", "volumes": volumes}


def cache_manifest() -> dict:
    """Return the deterministic inputs that define the projection cache."""
    manifest = {
        "code_version": CODE_VERSION,
        "profile": PROFILE,
        "projection": {
            "version": PROJECTION_VERSION,
            "affine_policy": "voxel = inverse(volume_affine) @ explicit_surface_to_volume_world @ surface_RAS",
            "registration": registration(),
            "ribbon_depths": list(RIBBON_DEPTHS),
            "nonfinite_policy": "mask invalid corners and vertices; finite weighted mean only",
        },
        "geometry": _geometry_manifest(),
        "signatures": _volume_manifest(),
    }
    return {**manifest, "sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def cache_identity() -> str:
    """Stable cache key including geometry, projection, signature and code IDs."""
    return cache_manifest()["sha256"]


def _volume_affine_manifest(path: Path) -> dict:
    import nibabel as nib
    image = nib.load(str(path))
    affine = np.asarray(image.affine, dtype=np.float64)
    try:
        from nibabel.orientations import aff2axcodes
        orientation = list(aff2axcodes(affine))
    except Exception:
        orientation = []
    return {
        "shape": list(image.shape), "affine_sha256": hashlib.sha256(affine.tobytes()).hexdigest(),
        "axis_codes": orientation,
    }


@lru_cache(maxsize=8)
def _signatures_cached(identity: str) -> tuple[dict[str, np.ndarray], dict]:
    result: dict[str, np.ndarray] = {}
    coverages: dict[str, float] = {}
    volume_hashes: dict[str, str | None] = {}
    affine: dict[str, dict] = {}
    vector_hashes: dict[str, str] = {}
    for emotion in EMOTIONS:
        path = _volume_path(emotion)
        vector, coverage = _sample_volume(path)
        finite = np.isfinite(vector)
        if finite.mean() < 0.35:
            raise ValueError(f"Kragel {emotion} projection covers only {finite.mean():.1%} of fsaverage5")
        centered = np.where(finite, vector - float(np.nanmean(vector)), 0.0)
        norm = np.linalg.norm(centered)
        if not np.isfinite(norm) or norm < 1e-9:
            raise ValueError(f"Kragel {emotion} projection is degenerate")
        normalized = centered / norm
        if not np.isfinite(normalized).all():
            raise ValueError(f"Kragel {emotion} projection contains non-finite values")
        result[emotion] = normalized
        coverages[emotion] = coverage
        volume_hashes[emotion] = _sha256(path)
        affine[emotion] = _volume_affine_manifest(path)
        vector_hashes[emotion] = hashlib.sha256(normalized.tobytes()).hexdigest()
    manifest = cache_manifest()
    provenance = {
        "contract_version": PROVENANCE_VERSION,
        "model": {"name": "Kragel 2015 BPLS", "version": "2015"},
        "checkpoint": {"sha256": None, "version": "published signature volumes"},
        "preprocessing": {"version": "tribe-row-centering-v1", "sha256": None, "meaning": "TRIBE cortical response is centered per row"},
        "geometry": {**manifest["geometry"]},
        "projection": {**manifest["projection"], "sha256": manifest["sha256"], "volume_affine": affine},
        "signature": {**manifest["signatures"], "vector_sha256": vector_hashes},
        "cache_identity": identity,
        "coverage": coverages,
        "volume_sha256": volume_hashes,
        "profile": PROFILE,
    }
    return result, provenance


def signatures() -> tuple[dict[str, np.ndarray], dict]:
    state = status()
    if state["status"] != "experimental_ready":
        raise RuntimeError("Kragel assets are incomplete: " + ", ".join(state["missing"]))
    identity = cache_identity()
    return _signatures_cached(identity)


# Keep the useful cache-management affordance on the historical public name.
signatures.cache_clear = _signatures_cached.cache_clear  # type: ignore[attr-defined]


def _time_axis(times: list[float], durations: list[float] | None, source_duration: float | None) -> tuple[list[dict[str, Any]], float, list[float]]:
    if not times:
        raise ValueError("TRIBE timestamps are required for Kragel decoding")
    starts = [float(value) for value in times]
    if any(not np.isfinite(value) for value in starts) or any(value < 0 for value in starts):
        raise ValueError("TRIBE timestamps must be finite and non-negative")
    if starts != sorted(starts):
        raise ValueError("TRIBE timestamps must be ordered")
    if durations is not None:
        if len(durations) != len(starts):
            raise ValueError("TRIBE segment durations do not match response rows")
        lengths = [float(value) for value in durations]
        if any(not np.isfinite(value) or value <= 0 for value in lengths):
            raise ValueError("TRIBE segment durations must be finite and positive")
    else:
        lengths = []
        for index, start in enumerate(starts):
            if index + 1 < len(starts):
                lengths.append(starts[index + 1] - start)
            elif source_duration is not None:
                lengths.append(float(source_duration) - start)
            elif index:
                lengths.append(starts[-1] - starts[-2])
            else:
                lengths.append(1.0)
    ends = [start + length for start, length in zip(starts, lengths)]
    inferred_duration = max(ends)
    duration = inferred_duration if source_duration is None else float(source_duration)
    if not np.isfinite(duration) or duration <= 0 or duration < inferred_duration - 1e-9:
        raise ValueError("TRIBE source duration must cover every segment")
    axis = normalized_axis([{"start": start, "end": end} for start, end in zip(starts, ends)], duration, source="kragel")
    return axis, duration, lengths


def decode_source_supported(response: np.ndarray, times: list[float], durations: list[float], source_duration: float) -> dict:
    """Exclude padded TRIBE windows with no overlap with the actual stimulus."""
    if len(response) != len(times) or len(times) != len(durations):
        raise ValueError('TRIBE interval lengths do not match response rows')
    if not np.isfinite(source_duration) or source_duration <= 0:
        raise ValueError('Source duration must be finite and positive')
    if any(not np.isfinite(t) or t < 0 for t in times) or any(not np.isfinite(d) or d <= 0 for d in durations):
        raise ValueError('Invalid original TRIBE intervals')
    indices = [i for i, start in enumerate(times) if start < source_duration]
    if not indices:
        raise ValueError('No TRIBE interval overlaps the source')
    starts = [times[i] for i in indices]
    lengths = [min(durations[i], source_duration-times[i]) for i in indices]
    result = decode(np.asarray(response)[indices], starts, lengths, source_duration)
    result['excluded_padding_rows'] = [i for i in range(len(times)) if i not in indices]
    result['time_note'] = 'Diagnostic support is clipped to the actual source; zero-overlap padded rows are excluded. Raw TRIBE windows remain in cortical evidence.'
    return result


def decode(response: np.ndarray, times: list[float], durations: list[float] | None = None, source_duration: float | None = None) -> dict:
    x = validate_response(response)
    if len(times) != len(x):
        raise ValueError("TRIBE timestamps do not match response rows")
    axis, duration, segment_durations = _time_axis(times, durations, source_duration)
    patterns, provenance = signatures()
    centered = x - x.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(centered, axis=1, keepdims=True)
    if np.any(~np.isfinite(norms)) or np.any(norms < 1e-12):
        raise ValueError("Degenerate or non-finite TRIBE row cannot be decoded")
    normalized = centered / norms
    trajectories = {emotion: (normalized @ vector).astype(float).tolist() for emotion, vector in patterns.items()}
    if any(not np.isfinite(value) for values in trajectories.values() for value in values):
        raise ValueError("Kragel decoding produced non-finite trajectories")
    aggregate = {emotion: float(np.mean(values)) for emotion, values in trajectories.items()}
    top = max(aggregate, key=aggregate.get)
    return {
        "registration_verified": provenance["projection"]["registration"]["verified"],
        "decision_eligible": False, "cannot_be_used_for_decisions": True,
        "status": "experimental", "evaluator": "Kragel 2015 BPLS emotion signatures", "profile": PROFILE,
        "source_kind": "tribe_derived", "labels": list(EMOTIONS), "times": [float(value) for value in times],
        "segment_durations": segment_durations, "source_duration": duration, "time_axis": axis,
        "trajectories": trajectories, "aggregate": aggregate, "top_pattern": top,
        "hemisphere_order": list(HEMISPHERES), "ribbon_depths": list(RIBBON_DEPTHS),
        "provenance": provenance,
        "interpretation": "Diagnostic spatial pattern-expression correlations. Registration and transfer validation are separate requirements; these outputs are not eligible for optimization decisions.",
        "limitations": [
            "Experimental model-to-model transfer, not a calibrated probability or observed viewer emotion.",
            "Kragel signatures were derived from measured fMRI; transfer to TRIBE synthetic predictions is not independently validated.",
            "The complete surface-to-volume spatial registration is unverified unless an exact-asset review receipt is present; inverse volume affine alone is not registration.",
        ],
    }
