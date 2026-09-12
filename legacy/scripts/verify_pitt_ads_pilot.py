#!/usr/bin/env python3
"""Verify a downloaded Pitt image-ad pilot without network or model access.

The verifier is deliberately read-only and stdlib-only. It checks the manifest,
local image inventory, per-file byte counts and SHA-256 digests, provenance URLs,
majority-vote annotations, and the expected balanced label counts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_BASE = "https://huggingface.co/datasets/Mindykkyan/PittadsDB-AdsPics/resolve/main"
TARGET_LABELS = {
    "1": "active",
    "5": "amazed",
    "7": "angry",
    "8": "calm",
    "9": "cheerful",
    "10": "confident",
    "12": "creative",
    "16": "emotional",
    "21": "inspired",
    "28": "sad",
}
REQUIRED_FIELDS = (
    "local_file",
    "source_key",
    "source_url",
    "target_label",
    "target_name",
    "target_votes",
    "annotator_count",
    "all_annotator_labels",
    "bytes",
    "sha256",
)
IMAGE_DIR_NAME = "images"
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class VerificationResult:
    root: str
    expected_count: int
    row_count: int = 0
    image_file_count: int = 0
    unique_source_keys: int = 0
    unique_sha256: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "PASS_WITH_WARNINGS"
        return "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "root": self.root,
            "expected_count": self.expected_count,
            "row_count": self.row_count,
            "image_file_count": self.image_file_count,
            "unique_source_keys": self.unique_source_keys,
            "unique_sha256": self.unique_sha256,
            "label_counts": dict(self.label_counts),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def valid_expected_count(value: int) -> bool:
    return 50 <= value <= 100 and value % len(TARGET_LABELS) == 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_kind(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(PNG_SIGNATURE):
        return "png"
    return None


def safe_local_path(root: Path, raw: str) -> Path | None:
    candidate = Path(raw)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        return None
    if candidate.parts[0] != IMAGE_DIR_NAME:
        return None
    resolved_root = root.resolve()
    resolved_candidate = (root / candidate).resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return root / candidate


def _read_manifest(root: Path, result: VerificationResult) -> list[tuple[int, dict[str, str]]]:
    manifest_path = root / "manifest.csv"
    if not manifest_path.is_file():
        result.errors.append("missing manifest.csv")
        return []
    try:
        with manifest_path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)):
                result.errors.append("manifest.csv has duplicate column names")
            missing = sorted(set(REQUIRED_FIELDS) - set(headers))
            if missing:
                result.errors.append("manifest.csv missing columns: " + ", ".join(missing))
            extra = sorted(set(headers) - set(REQUIRED_FIELDS))
            if extra:
                result.warnings.append("manifest.csv has extra columns: " + ", ".join(extra))
            rows: list[tuple[int, dict[str, str]]] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    result.errors.append(f"manifest row {line_number} has extra fields")
                normalized = {
                    key: (value or "")
                    for key, value in row.items()
                    if key is not None
                }
                rows.append((line_number, normalized))
            return rows
    except (OSError, UnicodeError, csv.Error) as error:
        result.errors.append(f"could not read manifest.csv: {error}")
        return []


def _check_source_legend(root: Path, result: VerificationResult) -> None:
    legend_path = root / "source-sentiments-list.txt"
    if not legend_path.is_file():
        result.errors.append("missing source-sentiments-list.txt")
        return
    try:
        legend = legend_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        result.errors.append(f"could not read source-sentiments-list.txt: {error}")
        return
    for label_id, label_name in TARGET_LABELS.items():
        marker = f'(ABBREVIATION: "{label_name}")'
        if marker not in legend:
            result.errors.append(
                f"source-sentiments-list.txt does not contain label {label_id} ({label_name})"
            )


def _check_image_inventory(root: Path, result: VerificationResult) -> set[str]:
    image_dir = root / IMAGE_DIR_NAME
    if not image_dir.is_dir():
        result.errors.append("missing images/ directory")
        return set()
    inventory: set[str] = set()
    for path in sorted(image_dir.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result.errors.append(f"image inventory contains symlink: {relative}")
        elif path.is_file():
            inventory.add(relative)
    result.image_file_count = len(inventory)
    return inventory


def verify_pack(
    pack_dir: Path,
    expected_count: int = 50,
    *,
    strict_unique: bool = False,
) -> VerificationResult:
    """Return deterministic read-only checks for one downloaded pilot folder."""

    root = pack_dir.expanduser().resolve()
    result = VerificationResult(
        root=str(root),
        expected_count=expected_count,
        label_counts={name: 0 for name in TARGET_LABELS.values()},
    )
    if not valid_expected_count(expected_count):
        result.errors.append("expected_count must be a multiple of 10 between 50 and 100")
        return result
    if not root.is_dir():
        result.errors.append("pack directory does not exist or is not a directory")
        return result

    rows = _read_manifest(root, result)
    result.row_count = len(rows)
    if result.row_count != expected_count:
        result.errors.append(
            f"manifest row count is {result.row_count}; expected {expected_count}"
        )

    _check_source_legend(root, result)
    inventory = _check_image_inventory(root, result)
    local_paths: list[str] = []
    source_keys: list[str] = []
    hashes: list[str] = []
    observed_names: Counter[str] = Counter()
    expected_per_label = expected_count // len(TARGET_LABELS)

    for line_number, row in rows:
        missing_fields = sorted(field for field in REQUIRED_FIELDS if not row.get(field, ""))
        if missing_fields:
            result.errors.append(
                f"manifest row {line_number} missing values: {', '.join(missing_fields)}"
            )
            continue

        local_file = row["local_file"]
        local_path = safe_local_path(root, local_file)
        if local_path is None:
            result.errors.append(f"manifest row {line_number} has unsafe local_file: {local_file}")
        else:
            local_paths.append(Path(local_file).as_posix())
            if local_path.is_symlink():
                result.errors.append(f"manifest row {line_number} points to a symlink: {local_file}")
            elif not local_path.is_file():
                result.errors.append(f"manifest row {line_number} points to missing file: {local_file}")
            else:
                suffix = local_path.suffix.lower()
                if suffix not in ALLOWED_SUFFIXES:
                    result.errors.append(f"manifest row {line_number} has unsupported image suffix: {local_file}")
                try:
                    payload = local_path.read_bytes()
                    kind = image_kind(payload)
                    if kind is None:
                        result.errors.append(f"manifest row {line_number} is not a JPEG or PNG: {local_file}")
                    elif (suffix in {".jpg", ".jpeg"} and kind != "jpeg") or (
                        suffix == ".png" and kind != "png"
                    ):
                        result.errors.append(f"manifest row {line_number} extension does not match image bytes: {local_file}")
                    declared_bytes = int(row["bytes"])
                    if declared_bytes < 1:
                        result.errors.append(f"manifest row {line_number} has non-positive bytes: {local_file}")
                    elif declared_bytes != len(payload):
                        result.errors.append(
                            f"manifest row {line_number} byte count mismatch: {local_file}"
                        )
                    declared_hash = row["sha256"]
                    if not re.fullmatch(r"[0-9a-f]{64}", declared_hash):
                        result.errors.append(f"manifest row {line_number} has non-canonical sha256: {local_file}")
                    actual_hash = sha256_file(local_path)
                    if declared_hash != actual_hash:
                        result.errors.append(f"manifest row {line_number} sha256 mismatch: {local_file}")
                    hashes.append(actual_hash)
                except (OSError, ValueError):
                    result.errors.append(f"manifest row {line_number} has unreadable image metadata: {local_file}")

        source_key = row["source_key"]
        source_path = Path(source_key)
        if source_path.is_absolute() or not source_path.parts or ".." in source_path.parts:
            result.errors.append(f"manifest row {line_number} has unsafe source_key: {source_key}")
        expected_url = f"{REPO_BASE}/images/{source_key}"
        if row["source_url"] != expected_url:
            result.errors.append(f"manifest row {line_number} source_url does not match source_key")
        source_keys.append(source_key)

        target_label = row["target_label"]
        target_name = row["target_name"]
        if target_label not in TARGET_LABELS:
            result.errors.append(f"manifest row {line_number} has unknown target_label: {target_label}")
        elif TARGET_LABELS[target_label] != target_name:
            result.errors.append(f"manifest row {line_number} label id/name mismatch")
        else:
            observed_names[target_name] += 1

        try:
            annotations = json.loads(row["all_annotator_labels"])
            if not isinstance(annotations, list) or not annotations:
                raise ValueError("annotation list is empty")
            if not all(isinstance(annotator, list) and annotator for annotator in annotations):
                raise ValueError("each annotator entry must be a non-empty list")
            normalized = [{str(value) for value in annotator} for annotator in annotations]
            computed_votes = sum(target_label in annotator for annotator in normalized)
            declared_annotators = int(row["annotator_count"])
            declared_votes = int(row["target_votes"])
            if declared_annotators != len(annotations):
                result.errors.append(f"manifest row {line_number} annotator_count mismatch")
            if declared_votes != computed_votes:
                result.errors.append(f"manifest row {line_number} target_votes mismatch")
            if declared_votes < math.ceil(len(annotations) / 2):
                result.errors.append(f"manifest row {line_number} does not have a majority vote")
        except (TypeError, ValueError, json.JSONDecodeError):
            result.errors.append(f"manifest row {line_number} has invalid all_annotator_labels")

    result.label_counts.update(
        {name: observed_names.get(name, 0) for name in TARGET_LABELS.values()}
    )
    unknown_names = sorted(set(observed_names) - set(TARGET_LABELS.values()))
    if unknown_names:
        result.errors.append("unknown target_name values: " + ", ".join(unknown_names))
    for name in TARGET_LABELS.values():
        if result.label_counts[name] != expected_per_label:
            result.errors.append(
                f"label count for {name} is {result.label_counts[name]}; expected {expected_per_label}"
            )

    duplicate_local_paths = sorted(
        path for path, count in Counter(local_paths).items() if count > 1
    )
    if duplicate_local_paths:
        result.errors.append("duplicate local_file values: " + ", ".join(duplicate_local_paths))
    missing_files = sorted(set(local_paths) - inventory)
    unlisted_files = sorted(inventory - set(local_paths))
    if missing_files:
        result.errors.append("manifest files missing from images/: " + ", ".join(missing_files))
    if unlisted_files:
        result.errors.append("unlisted files under images/: " + ", ".join(unlisted_files))

    source_counts = Counter(source_keys)
    hash_counts = Counter(hashes)
    result.unique_source_keys = len(source_counts)
    result.unique_sha256 = len(hash_counts)
    duplicate_sources = sorted((key, count) for key, count in source_counts.items() if count > 1)
    duplicate_hashes = sorted((digest, count) for digest, count in hash_counts.items() if count > 1)
    if duplicate_sources:
        message = "duplicate source_key values: " + ", ".join(
            f"{key} ({count} rows)" for key, count in duplicate_sources
        )
        (result.errors if strict_unique else result.warnings).append(message)
    if duplicate_hashes:
        message = "duplicate sha256 values: " + ", ".join(
            f"{digest} ({count} rows)" for digest, count in duplicate_hashes
        )
        (result.errors if strict_unique else result.warnings).append(message)

    result.errors.sort()
    result.warnings.sort()
    return result


def _human_report(result: VerificationResult) -> str:
    lines = [
        f"status: {result.status}",
        f"root: {result.root}",
        f"rows: {result.row_count}/{result.expected_count}",
        f"image_files: {result.image_file_count}",
        f"unique_source_keys: {result.unique_source_keys}",
        f"unique_sha256: {result.unique_sha256}",
        "label_counts: " + ", ".join(
            f"{name}={result.label_counts.get(name, 0)}" for name in TARGET_LABELS.values()
        ),
    ]
    for warning in result.warnings:
        lines.append("warning: " + warning)
    for error in result.errors:
        lines.append("error: " + error)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_dir",
        nargs="?",
        type=Path,
        default=Path("data/datasets/pitt-ads-sentiment-50"),
        help="downloaded pilot directory (default: data/datasets/pitt-ads-sentiment-50)",
    )
    parser.add_argument("--expected-count", type=int, default=50)
    parser.add_argument(
        "--strict-unique",
        action="store_true",
        help="treat repeated source IDs or repeated file hashes as errors",
    )
    parser.add_argument("--json", action="store_true", help="emit stable JSON instead of text")
    args = parser.parse_args(argv)
    result = verify_pack(
        args.pack_dir,
        expected_count=args.expected_count,
        strict_unique=args.strict_unique,
    )
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(_human_report(result))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
