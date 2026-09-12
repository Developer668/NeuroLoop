"""Experimental Kragel 2015 emotion-pattern expression on TRIBE fsaverage5 output.

The published Kragel BPLS maps are MNI-space volumes and higher-resolution surface
scalars. We do not index-resample the surface scalars. Instead, the volume maps are
sampled onto the documented fsaverage5 white-to-pial cortical ribbon used by TRIBE,
then compared with each spatially centered TRIBE time point.

The resulting values are pattern-expression correlations. They are experimental
model-to-model evidence, not calibrated probabilities or observed human emotions.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import settings
from .readout import validate_response

EMOTIONS = ("amused", "angry", "content", "fearful", "neutral", "sad", "surprised")
PROFILE = "kragel2015-bpls-mni-volume-to-fsaverage5-ribbon-v1"


def _source() -> Path:
    return settings().root / "models/brain_readouts/kragel2015/source"


def _geometry(name: str) -> Path:
    return settings().data / "geometry" / name


def _volume_path(emotion: str) -> Path:
    matches = sorted(_source().glob(f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.hdr"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Kragel {emotion} volume is missing")
    return matches[0]


@lru_cache(maxsize=1)
def fingerprint() -> str:
    """Content identity for the decoder, source maps, and projection geometry.

    This is intentionally separate from TRIBE's model profile so a Kragel-only
    change invalidates only evaluations that requested the decoder.
    """
    h = hashlib.sha256()
    h.update(PROFILE.encode())
    h.update(Path(__file__).read_bytes())
    for emotion in EMOTIONS:
        for suffix in ("hdr", "img"):
            path = _source() / f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.{suffix}"
            if path.is_file():
                h.update(path.name.encode())
                h.update(path.read_bytes())
    for hemi in ("left", "right"):
        for surface in ("pial", "white"):
            path = _geometry(f"{surface}_{hemi}.gii.gz")
            if path.is_file():
                h.update(path.name.encode())
                h.update(path.read_bytes())
    return f"{PROFILE}-{h.hexdigest()[:16]}"


def status() -> dict:
    required = [
        _source() / f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.hdr"
        for emotion in EMOTIONS
    ] + [
        _source() / f"mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.img"
        for emotion in EMOTIONS
    ]
    geometry = [_geometry(f"pial_{h}.gii.gz") for h in ("left", "right")] + [
        _geometry(f"white_{h}.gii.gz") for h in ("left", "right")
    ]
    missing = []
    for path in required + geometry:
        if not path.is_file():
            try:
                missing.append(str(path.relative_to(settings().root)))
            except ValueError:
                missing.append(str(path))
    return {
        "status": "experimental_ready" if not missing else "missing_assets",
        "profile": PROFILE,
        "fingerprint": fingerprint() if not missing else None,
        "missing": missing,
        "meaning": "Kragel 2015 BPLS pattern expression projected from published MNI volumes onto the TRIBE fsaverage5 cortical ribbon.",
    }


def _trilinear(data: np.ndarray, xyz_vox: np.ndarray) -> np.ndarray:
    """Vectorized trilinear interpolation. Samples outside the image become NaN."""
    shape = np.asarray(data.shape[:3])
    lo = np.floor(xyz_vox).astype(np.int64)
    frac = xyz_vox - lo
    valid = np.all(lo >= 0, axis=1) & np.all(lo + 1 < shape, axis=1)
    out = np.full(len(xyz_vox), np.nan, dtype=np.float64)
    if not np.any(valid):
        return out
    i = lo[valid]
    f = frac[valid]
    x0, y0, z0 = i[:, 0], i[:, 1], i[:, 2]
    x1, y1, z1 = x0 + 1, y0 + 1, z0 + 1
    fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
    v = (
        data[x0, y0, z0] * (1-fx)*(1-fy)*(1-fz)
        + data[x1, y0, z0] * fx*(1-fy)*(1-fz)
        + data[x0, y1, z0] * (1-fx)*fy*(1-fz)
        + data[x1, y1, z0] * fx*fy*(1-fz)
        + data[x0, y0, z1] * (1-fx)*(1-fy)*fz
        + data[x1, y0, z1] * fx*(1-fy)*fz
        + data[x0, y1, z1] * (1-fx)*fy*fz
        + data[x1, y1, z1] * fx*fy*fz
    )
    out[valid] = v
    return out


def _coords(path: Path) -> np.ndarray:
    import nibabel as nib
    image = nib.load(str(path))
    arrays = [np.asarray(d.data, dtype=np.float64) for d in image.darrays if d.intent == 1008]
    if len(arrays) != 1 or arrays[0].shape != (10242, 3):
        raise ValueError(f"Unexpected fsaverage5 geometry in {path.name}")
    return arrays[0]


def _sample_volume(volume_path: Path) -> tuple[np.ndarray, float]:
    import nibabel as nib
    image = nib.load(str(volume_path))
    data = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float64)
    if data.ndim != 3 or np.isfinite(data).mean() < 0.95:
        raise ValueError(f"Invalid Kragel volume {volume_path.name}")
    inverse = np.linalg.inv(image.affine)
    hemispheres = []
    coverage = []
    for hemi in ("left", "right"):
        pial = _coords(_geometry(f"pial_{hemi}.gii.gz"))
        white = _coords(_geometry(f"white_{hemi}.gii.gz"))
        # Sample five points through the cortical ribbon. This follows the same
        # geometry principle as volume-to-surface sampling without depending on
        # scipy/nilearn in the application runtime.
        samples = []
        for depth in np.linspace(0.0, 1.0, 5):
            world = white * (1.0-depth) + pial * depth
            homogeneous = np.c_[world, np.ones(len(world))]
            vox = (inverse @ homogeneous.T).T[:, :3]
            samples.append(_trilinear(data, vox))
        stacked = np.stack(samples)
        valid = np.isfinite(stacked)
        count = valid.sum(axis=0)
        values = np.divide(np.nansum(stacked, axis=0), count, out=np.full(10242, np.nan), where=count > 0)
        coverage.append(float(np.isfinite(values).mean()))
        hemispheres.append(values)
    return np.concatenate(hemispheres), float(np.mean(coverage))


@lru_cache(maxsize=1)
def signatures() -> tuple[dict[str, np.ndarray], dict]:
    state = status()
    if state["status"] != "experimental_ready":
        raise RuntimeError("Kragel assets are incomplete: " + ", ".join(state["missing"]))
    result: dict[str, np.ndarray] = {}
    coverages = {}
    hashes = {}
    for emotion in EMOTIONS:
        path = _volume_path(emotion)
        image_path = path.with_suffix(".img")
        vector, coverage = _sample_volume(path)
        finite = np.isfinite(vector)
        if finite.mean() < 0.35:
            raise ValueError(f"Kragel {emotion} projection covers only {finite.mean():.1%} of fsaverage5")
        # Missing cortical locations remain zero after centering over valid source
        # samples. They cannot create positive evidence by themselves.
        mean = float(np.nanmean(vector))
        vector = np.where(finite, vector - mean, 0.0)
        norm = np.linalg.norm(vector)
        if norm < 1e-9:
            raise ValueError(f"Kragel {emotion} projection is degenerate")
        result[emotion] = vector / norm
        coverages[emotion] = coverage
        hashes[emotion] = {
            "hdr": hashlib.sha256(path.read_bytes()).hexdigest(),
            "img": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        }
    geometry_hashes = {}
    for hemi in ("left", "right"):
        for surface in ("pial", "white"):
            geometry_path = _geometry(f"{surface}_{hemi}.gii.gz")
            geometry_hashes[f"{surface}_{hemi}"] = hashlib.sha256(geometry_path.read_bytes()).hexdigest()
    return result, {
        "coverage": coverages,
        "volume_sha256": hashes,
        "geometry_sha256": geometry_hashes,
        "profile": PROFILE,
        "fingerprint": fingerprint(),
    }


def decode(response: np.ndarray, times: list[float]) -> dict:
    x = validate_response(response)
    if len(times) != len(x):
        raise ValueError("TRIBE timestamps do not match response rows")
    patterns, provenance = signatures()
    centered = x - x.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(centered, axis=1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError("Degenerate TRIBE row cannot be decoded")
    normalized = centered / norms
    trajectories = {emotion: (normalized @ vector).astype(float).tolist() for emotion, vector in patterns.items()}
    aggregate = {emotion: float(np.mean(values)) for emotion, values in trajectories.items()}
    top = max(aggregate, key=aggregate.get)
    return {
        "status": "experimental",
        "evaluator": "Kragel 2015 BPLS emotion signatures",
        "profile": PROFILE,
        "labels": list(EMOTIONS),
        "times": [float(t) for t in times],
        "trajectories": trajectories,
        "aggregate": aggregate,
        "top_pattern": top,
        "provenance": provenance,
        "interpretation": "Spatial pattern-expression correlations between TRIBE-predicted cortical activity and Kragel 2015 emotion signatures.",
        "limitations": [
            "Experimental model-to-model transfer, not a calibrated probability or observed viewer emotion.",
            "Kragel signatures were derived from measured fMRI; transfer to TRIBE synthetic responses is not independently validated.",
            "Published MNI volumes are sampled onto fsaverage5 through the white-to-pial cortical ribbon; no arbitrary surface-index resampling is used.",
        ],
    }
