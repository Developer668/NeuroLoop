"""Verify the local model bundle without importing or executing model code.

Large weights intentionally stay outside Git.  This check makes a checkout
portable by proving that its local files are present and match the manifests
written when the approved bundle was downloaded.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []
checked: set[Path] = set()


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def describe(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_file(
    path: Path,
    *,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
) -> None:
    path = path.resolve()
    checked.add(path)
    name = describe(path)
    if not path.is_file():
        failures.append(f"missing: {name}")
        return
    actual_bytes = path.stat().st_size
    if expected_bytes is not None and actual_bytes != expected_bytes:
        failures.append(f"size mismatch: {name} ({actual_bytes} != {expected_bytes})")
    if expected_sha256 is not None:
        actual_sha256 = digest(path)
        if actual_sha256 != expected_sha256:
            failures.append(f"sha256 mismatch: {name} ({actual_sha256} != {expected_sha256})")


def read_json(path: Path) -> dict:
    check_file(path)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        failures.append(f"invalid JSON: {describe(path)} ({exc})")
        return {}
    if not isinstance(value, dict):
        failures.append(f"invalid manifest shape: {describe(path)}")
        return {}
    return value


def check_download_manifest(path: Path, base: Path) -> None:
    manifest = read_json(path)
    records = manifest.get("files", [])
    if not isinstance(records, list):
        failures.append(f"invalid file list: {describe(path)}")
        return
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("file"), str):
            failures.append(f"invalid file entry: {describe(path)}")
            continue
        check_file(
            base / record["file"],
            expected_bytes=record.get("bytes"),
            expected_sha256=record.get("sha256"),
        )


def main() -> int:
    # Text, audio, DINOv2 and TSAM manifests record the exact downloaded bytes.
    for relative in (
        "models/audio/w2v-bert-2.0/download-manifest.json",
        "models/text/llama-3.2-3b-unsloth-q4/download-manifest.json",
        "models/vision/dinov2-large/download-manifest.json",
        "models/emotion/tsam/weights/download-manifest.json",
        "models/brain_readouts/kragel2015/source/download-manifest.json",
    ):
        check_download_manifest(ROOT / relative, (ROOT / relative).parent)

    # The local Whisper bundle records sizes; its model.bin is not a Git file.
    whisper = ROOT / "models/preprocessing/faster-whisper-small/neuroloop-provenance.json"
    whisper_manifest = read_json(whisper)
    whisper_files = whisper_manifest.get("files", {})
    if isinstance(whisper_files, dict):
        for name, size in whisper_files.items():
            if isinstance(name, str) and isinstance(size, int):
                check_file(whisper.parent / name, expected_bytes=size)
            else:
                failures.append(f"invalid speech asset entry: {describe(whisper)}")

    # TRIBE's original brain checkpoint is immutable; only the binary is
    # checked here because Git may normalize the tracked text config files.
    tribe_provenance = read_json(ROOT / "tribev2-balanced-qv-local/provenance.json")
    checkpoint_sha = tribe_provenance.get("official_files_sha256", {}).get("best.ckpt")
    check_file(ROOT / "tribev2-balanced-qv-local/best.ckpt", expected_sha256=checkpoint_sha)

    quantization = read_json(ROOT / "tribev2-balanced-qv-local/quantized_video/quantization.json")
    check_file(
        ROOT / "tribev2-balanced-qv-local/quantized_video/model.safetensors",
        expected_bytes=quantization.get("quantized_bytes"),
        expected_sha256=quantization.get("quantized_sha256"),
    )
    for relative in (
        "tribev2-balanced-qv-local/quantized_video/config.json",
        "tribev2-balanced-qv-local/quantized_video/video_preprocessor_config.json",
    ):
        check_file(ROOT / relative)

    # Static geometry is tracked so a fresh clone can render the anatomy view.
    geometry = ROOT / "data/geometry"
    geometry_provenance = read_json(geometry / "provenance.json")
    for name, record in geometry_provenance.get("files", {}).items():
        if isinstance(record, dict):
            check_file(
                geometry / name,
                expected_bytes=record.get("bytes"),
                expected_sha256=record.get("sha256"),
            )
    atlas = read_json(geometry / "atlas.json")
    if atlas and (
        atlas.get("mesh") != "fsaverage5"
        or len(atlas.get("left", [])) != 10242
        or len(atlas.get("right", [])) != 10242
    ):
        failures.append("invalid Destrieux atlas dimensions: data/geometry/atlas.json")
    surface = read_json(geometry / "fsaverage5.json")
    hemispheres = surface.get("hemispheres", [])
    if surface and (
        surface.get("mesh") != "fsaverage5"
        or len(hemispheres) != 2
        or any(len(item.get("positions", [])) != 10242 * 3 for item in hemispheres)
        or any(len(item.get("indices", [])) != 20480 * 3 for item in hemispheres)
    ):
        failures.append("invalid fsaverage5 geometry dimensions: data/geometry/fsaverage5.json")

    wheel_provenance = read_json(ROOT / "infrastructure/wheels/provenance.json")
    check_file(
        ROOT / "infrastructure/wheels/en_core_web_lg-3.8.0-py3-none-any.whl",
        expected_bytes=wheel_provenance.get("bytes"),
        expected_sha256=wheel_provenance.get("sha256"),
    )

    if failures:
        print(f"Local asset check failed ({len(failures)} issue(s)):")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Local asset check passed: {len(checked)} files verified.")
    print("Model execution remains governed by data/inference-quarantine.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
