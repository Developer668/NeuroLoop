"""Build the upload bundle for the Molab all-model research notebook.

The bundle contains the local-only quantized TRIBE stack plus TSAM and Kragel
assets. Public Hugging Face support models remain pinned in the manifest and
are downloaded by the notebook so that this archive stays reviewable.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import zipfile


SOURCE_ROOT = Path(r"D:\NeuroLoopV1")
OUTPUT_ROOT = Path(r"D:\NeuroLoop\artifacts\molab")
ARCHIVE = OUTPUT_ROOT / "neuroloop-research-runtime.zip"
MANIFEST = OUTPUT_ROOT / "neuroloop-research-runtime.manifest.json"

INCLUDE = (
    "tribev2-balanced-qv-local/load_quantized_tribev2.py",
    "tribev2-balanced-qv-local/config.yaml",
    "tribev2-balanced-qv-local/verification.json",
    "tribev2-balanced-qv-local/provenance.json",
    "tribev2-balanced-qv-local/LICENSE",
    "tribev2-balanced-qv-local/quantized_video",
    "models/load_local_tribe.py",
    "models/emotion/tsam",
    "models/brain_readouts/kragel2015",
    "data/geometry",
    "backend/neuroloop",
    "infrastructure/vendor/tribev2",
)

PINNED_PUBLIC_MODELS = {
    "tribev2": {"repo": "facebook/tribev2", "revision": "f894e783020944dcd96e5568550afe2aa9743f9f"},
    "w2v_bert": {"repo": "facebook/w2v-bert-2.0", "revision": "da985ba0987f70aaeb84a80f2851cfac8c697a7b"},
    "dinov2_large": {"repo": "facebook/dinov2-large", "revision": "47b73eefe95e8d44ec3623f8890bd894b6ea2d6c"},
    "llama_3_2_3b_q4": {"repo": "unsloth/Llama-3.2-3B-bnb-4bit", "revision": "cd129a0e0b128fe4fb01e1bdca5e9af6a0c9a5d6"},
    "faster_whisper_small": {"repo": "Systran/faster-whisper-small", "revision": None},
}


def iter_files(path: Path):
    if path.is_file():
        yield path
        return
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in file.parts):
            continue
        if file.suffix in {".pyc", ".pyo"}:
            continue
        yield file


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for relative in INCLUDE:
        source = SOURCE_ROOT / relative
        if not source.exists():
            raise FileNotFoundError(source)
        files.extend(iter_files(source))

    records = []
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for source in sorted(set(files)):
            relative = source.relative_to(SOURCE_ROOT).as_posix()
            record = {"path": relative, "bytes": source.stat().st_size, "sha256": sha256(source)}
            records.append(record)
            archive.write(source, relative)
        embedded = json.dumps({"files": records, "pinned_public_models": PINNED_PUBLIC_MODELS}, indent=2)
        archive.writestr("BUNDLE_MANIFEST.json", embedded)

    result = {
        "archive": str(ARCHIVE),
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_sha256": sha256(ARCHIVE),
        "files": records,
        "pinned_public_models": PINNED_PUBLIC_MODELS,
    }
    MANIFEST.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "archive": str(ARCHIVE),
        "bytes": result["archive_bytes"],
        "sha256": result["archive_sha256"],
        "files": len(records),
    }))


if __name__ == "__main__":
    main()
