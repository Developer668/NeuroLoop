"""Focused, model-free tests for the Pitt labeled image-ad pilot."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = ROOT / "scripts" / "verify_pitt_ads_pilot.py"
DOWNLOADER_PATH = ROOT / "scripts" / "download_pitt_ads_pilot.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = load_module(VERIFIER_PATH, "verify_pitt_ads_pilot_test_module")
DOWNLOADER = load_module(DOWNLOADER_PATH, "download_pitt_ads_pilot_test_module")


JPEG_SIGNATURE = b"\xff\xd8\xff\xe0JFIF\x00"


def write_fixture_pack(root: Path, *, duplicate_hash: bool = False) -> None:
    images = root / "images"
    images.mkdir(parents=True)
    names = list(VERIFIER.TARGET_LABELS.values())
    rows = []
    legend = []
    for label_id, label_name in VERIFIER.TARGET_LABELS.items():
        legend.append(f'{label_id}. "Label" (ABBREVIATION: "{label_name}")')
    (root / "source-sentiments-list.txt").write_text("\n".join(legend), encoding="utf-8")
    (root / "README.md").write_text(
        "Static image ads with human sentiment annotations; no audio for TSAM.",
        encoding="utf-8",
    )
    for index in range(50):
        label_index = index // 5
        label_id = list(VERIFIER.TARGET_LABELS)[label_index]
        label_name = names[label_index]
        source_key = f"0/{100000 + index}.jpg"
        payload = JPEG_SIGNATURE + bytes([index])
        if duplicate_hash and index == 49:
            payload = (images / "001-active-100000.jpg").read_bytes()
        local_file = f"images/{index + 1:03d}-{label_name}-{100000 + index}.jpg"
        destination = root / local_file
        destination.write_bytes(payload)
        rows.append(
            {
                "local_file": local_file,
                "source_key": source_key,
                "source_url": f"{VERIFIER.REPO_BASE}/images/{source_key}",
                "target_label": label_id,
                "target_name": label_name,
                "target_votes": "3",
                "annotator_count": "3",
                "all_annotator_labels": json.dumps([[label_id], [label_id], [label_id]]),
                "bytes": str(len(payload)),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(VERIFIER.REQUIRED_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def test_verifier_accepts_balanced_hashed_pack(tmp_path):
    write_fixture_pack(tmp_path)

    result = VERIFIER.verify_pack(tmp_path)

    assert result.status == "PASS"
    assert result.row_count == 50
    assert result.image_file_count == 50
    assert result.unique_source_keys == 50
    assert result.unique_sha256 == 50
    assert result.label_counts == {name: 5 for name in VERIFIER.TARGET_LABELS.values()}


def test_verifier_rejects_hash_and_label_count_drift(tmp_path):
    write_fixture_pack(tmp_path)
    image_path = tmp_path / "images" / "001-active-100000.jpg"
    image_path.write_bytes(image_path.read_bytes() + b"changed")
    manifest_path = tmp_path / "manifest.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[5]["target_label"] = "1"
    rows[5]["target_name"] = "active"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(VERIFIER.REQUIRED_FIELDS))
        writer.writeheader()
        writer.writerows(rows)

    result = VERIFIER.verify_pack(tmp_path)

    assert result.status == "FAIL"
    assert any("sha256 mismatch" in error for error in result.errors)
    assert any("label count for active" in error for error in result.errors)
    assert any("label count for amazed" in error for error in result.errors)


def test_verifier_reports_duplicate_hash_without_hiding_it(tmp_path):
    write_fixture_pack(tmp_path, duplicate_hash=True)

    result = VERIFIER.verify_pack(tmp_path)
    strict_result = VERIFIER.verify_pack(tmp_path, strict_unique=True)

    assert result.status == "PASS_WITH_WARNINGS"
    assert result.unique_sha256 == 49
    assert any("duplicate sha256" in warning for warning in result.warnings)
    assert strict_result.status == "FAIL"


def test_downloader_does_not_reuse_a_source_across_labels():
    annotations = {}
    duplicate_source = "0/000-duplicate.jpg"
    annotations[duplicate_source] = [["1"], ["5"]]
    for label_id in DOWNLOADER.TARGET_LABELS:
        if label_id == "1":
            continue
        annotations.setdefault(f"0/alternate-{label_id}.jpg", [[label_id]])
    annotations["0/alternate-1.jpg"] = [["1"]]

    rows = DOWNLOADER.choose_rows(annotations, per_label=1)
    source_keys = [str(row["source_key"]) for row in rows]

    assert len(source_keys) == len(set(source_keys))
    assert source_keys[0] == duplicate_source
    assert source_keys[1] != duplicate_source
