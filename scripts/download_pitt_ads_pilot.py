#!/usr/bin/env python3
"""Download a small, labeled Pitt image-ad pilot without pulling the full corpus.

The upstream mirror exposes individual JPEGs and a sentiment annotation JSON.
This script selects a deterministic, label-balanced subset and writes only the
selected images plus a provenance manifest to the requested output directory.
It intentionally uses the stdlib so it does not import NeuroLoop or any model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_BASE = "https://huggingface.co/datasets/Mindykkyan/PittadsDB-AdsPics/resolve/main"
ANNOTATIONS_URL = f"{REPO_BASE}/image_annotations/image/Sentiments.json"
LABELS_URL = f"{REPO_BASE}/image_annotations/image/Sentiments_List.txt"

# Ten affective/attitudinal classes with enough majority-vote examples for a
# small balanced pilot. IDs follow the upstream Sentiments_List.txt order.
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


def fetch_bytes(url: str, retries: int = 3) -> bytes:
    request = Request(url, headers={"User-Agent": "NeuroLoop-labeled-pilot/1.0"})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"download failed for {url}: {last_error}")


def majority_target(annotations: list[list[str]], target: str) -> tuple[int, int] | None:
    if not annotations:
        return None
    votes = sum(target in {str(value) for value in annotator} for annotator in annotations)
    minimum = math.ceil(len(annotations) / 2)
    if votes < minimum:
        return None
    return votes, len(annotations)


def choose_rows(annotations: dict[str, list[list[str]]], per_label: int) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    used_source_keys: set[str] = set()
    for label_id, label_name in TARGET_LABELS.items():
        candidates: list[dict[str, object]] = []
        for source_key in sorted(annotations):
            # An ad can have a majority vote for more than one upstream
            # sentiment. Keep the pilot at the requested number of distinct
            # source ads instead of counting the same source once per label.
            if source_key in used_source_keys:
                continue
            votes = majority_target(annotations[source_key], label_id)
            if votes is None:
                continue
            candidates.append(
                {
                    "source_key": source_key,
                    "target_label": label_id,
                    "target_name": label_name,
                    "target_votes": votes[0],
                    "annotator_count": votes[1],
                    "all_annotator_labels": json.dumps(annotations[source_key], separators=(",", ":")),
                }
            )
        if len(candidates) < per_label:
            raise RuntimeError(
                f"only {len(candidates)} majority-vote examples available for {label_id} ({label_name}); "
                f"need {per_label}"
            )
        chosen = candidates[:per_label]
        selected.extend(chosen)
        used_source_keys.update(str(row["source_key"]) for row in chosen)
    return selected


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()
    if args.count < len(TARGET_LABELS) or args.count % len(TARGET_LABELS):
        raise SystemExit(
            f"--count must be a multiple of {len(TARGET_LABELS)} between 50 and 100 "
            "for a balanced pilot"
        )
    per_label = args.count // len(TARGET_LABELS)
    if not 50 <= args.count <= 100:
        raise SystemExit("--count must be between 50 and 100")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output directory: {args.output}")

    annotations = json.loads(fetch_bytes(ANNOTATIONS_URL).decode("utf-8"))
    rows = choose_rows(annotations, per_label)
    args.output.mkdir(parents=True)
    images_dir = args.output / "images"
    images_dir.mkdir()

    label_text = fetch_bytes(LABELS_URL).decode("utf-8", errors="replace")
    write_text(args.output / "source-sentiments-list.txt", label_text)

    manifest_path = args.output / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
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
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            source_key = str(row["source_key"])
            image_url = f"{REPO_BASE}/images/{source_key}"
            destination = images_dir / f"{index:03d}-{row['target_name']}-{Path(source_key).name}"
            destination.write_bytes(fetch_bytes(image_url))
            payload = destination.read_bytes()
            row.update(
                {
                    "local_file": str(destination.relative_to(args.output)),
                    "source_url": image_url,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            writer.writerow(row)
            print(f"[{index:02d}/{len(rows)}] {row['target_name']}: {destination.name}", flush=True)

    readme = f"""# Pitt labeled ad pilot

This folder contains exactly {len(rows)} individual image advertisements selected from the public
`Mindykkyan/PittadsDB-AdsPics` mirror of the University of Pittsburgh Ads dataset.

Selection is deterministic and balanced across ten upstream sentiment classes:
`{', '.join(TARGET_LABELS.values())}`. Each selected item has a majority-vote
annotation in `manifest.csv`; `all_annotator_labels` preserves the raw per-annotator
labels for that item.

The images are static ads. They can be used with NeuroLoop's explicit experimental
static-image/TRIBE presentation path, but they do not provide audio and therefore do
not validate the TSAM audiovisual branch. The labels are ad-perception annotations,
not measured cortical responses and not calibrated probabilities.

Source annotation: {ANNOTATIONS_URL}
Source label legend: {LABELS_URL}
Generated by: `scripts/download_pitt_ads_pilot.py`

The upstream mirror and original project do not establish a redistributable license
for the ad images here. Keep the source/provenance fields, use only within the
permissions that apply to your intended research/demo, and do not publish or ship
the images commercially without confirming rights.
"""
    write_text(args.output / "README.md", readme)
    print(f"Downloaded {len(rows)} labeled ads to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
