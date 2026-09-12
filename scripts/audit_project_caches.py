#!/usr/bin/env python3
"""Inventory NeuroLoop cache behavior without changing the filesystem.

This module intentionally has no cleanup implementation.  It reports disk
paths, a narrow manual-review allowlist, and optional host-memory telemetry so
that project disk caches are not confused with live unified-memory pressure.
The default output and ``--dry-run`` output are both read-only.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import platform
import re
import resource
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
DEFAULT_MAX_ENTRIES = 250_000
MAX_ERRORS = 8
MAX_CHILDREN = 12
EPHEMERAL_RESULT_NAMES = {"audio-16k.wav", "presentation.mp4"}
RESULT_KEY = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PathSpec:
    """A path with an explicit retention policy."""

    key: str
    path: Path
    kind: str
    ownership: str
    policy: str
    note: str
    scan: bool = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def human_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.2f} TiB"


def absolute(path: Path) -> Path:
    """Return an absolute path without requiring it to exist."""

    if path.is_absolute():
        return path
    return Path.cwd() / path


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _error(errors: list[str], message: str) -> None:
    if len(errors) < MAX_ERRORS:
        errors.append(message)


def scan_tree(path: Path, max_entries: int) -> dict[str, Any]:
    """Count a tree without following symlinked directories."""

    total_bytes = 0
    files = 0
    directories = 0
    symlinks = 0
    visited_entries = 0
    truncated = False
    errors: list[str] = []
    pending = [path]

    while pending and not truncated:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    visited_entries += 1
                    if visited_entries > max_entries:
                        truncated = True
                        break
                    try:
                        if entry.is_symlink():
                            symlinks += 1
                        elif entry.is_dir(follow_symlinks=False):
                            directories += 1
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            files += 1
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                    except OSError as exc:
                        _error(errors, f"{entry.path}: {exc}")
        except OSError as exc:
            _error(errors, f"{current}: {exc}")

    return {
        "bytes": total_bytes,
        "human_size": human_bytes(total_bytes),
        "files": files,
        "directories": directories,
        "symlinks_not_followed": symlinks,
        "entries_scanned": min(visited_entries, max_entries),
        "truncated": truncated,
        "errors": errors,
    }


def direct_children(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    try:
        names = sorted((entry.name for entry in os.scandir(path)), key=str.casefold)
    except OSError:
        return []
    return names[:MAX_CHILDREN]


def describe(spec: PathSpec, root: Path, max_entries: int) -> dict[str, Any]:
    path = absolute(spec.path)
    record: dict[str, Any] = {
        "key": spec.key,
        "path": str(path),
        "relative_path": display_path(path, root),
        "kind": spec.kind,
        "ownership": spec.ownership,
        "retention_policy": spec.policy,
        "note": spec.note,
        "exists": path.exists() or path.is_symlink(),
        "scan_policy": "recursive_without_following_symlinked_directories" if spec.scan else "presence_only",
    }
    if not record["exists"]:
        record.update({"bytes": None, "human_size": "missing", "files": 0, "directories": 0})
        return record

    try:
        stat = path.stat()
        record["modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        record["is_directory"] = path.is_dir()
        record["is_symlink"] = path.is_symlink()
    except OSError as exc:
        record["stat_error"] = str(exc)
        return record

    if path.is_file():
        record.update({"bytes": stat.st_size, "human_size": human_bytes(stat.st_size), "files": 1, "directories": 0})
    elif path.is_dir() and spec.scan:
        record.update(scan_tree(path, max_entries))
        record["sample_children"] = direct_children(path)
    elif path.is_dir():
        record.update({"bytes": None, "human_size": "not scanned", "files": None, "directories": None})
        record["sample_children"] = direct_children(path)
    return record


def configured_uv_cache() -> tuple[Path, str]:
    configured = os.environ.get("UV_CACHE_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return absolute(path), "UV_CACHE_DIR"
    return Path.home() / ".cache" / "uv", "uv_default_on_unix"


def path_specs(root: Path) -> list[PathSpec]:
    uv_cache, uv_source = configured_uv_cache()
    del uv_source  # The source is reported separately in the top-level record.
    data = root / "data"
    return [
        PathSpec(
            "project_feature_cache",
            root / "cache",
            "disk_cache",
            "project",
            "manual_review_only",
            "Neuralset/TRIBE feature cache. It avoids recomputation but is not live MPS memory.",
        ),
        PathSpec(
            "tribe_loader_cache",
            root / "tribev2-balanced-qv-local" / "cache-int8",
            "disk_cache",
            "project",
            "preserve_by_default",
            "Vendor-loader cache and chunk intermediates; preserve unless a specific stale entry is reviewed.",
        ),
        PathSpec(
            "project_test_scratch",
            data / "tmp",
            "runtime_temp",
            "project",
            "narrow_manual_review_only",
            "Test-created scratch workspaces only; review active processes before any manual cleanup.",
        ),
        PathSpec(
            "project_renders",
            data / "renders",
            "derived_media",
            "project",
            "preserve_unless_unreferenced",
            "Generated media may still be user-visible or referenced by a run; not a cache by default.",
        ),
        PathSpec(
            "project_results",
            data / "results",
            "runtime_output",
            "project",
            "preserve",
            "Predictions, evidence, logs, and failure receipts are runtime state and must be retained.",
        ),
        PathSpec(
            "project_assets",
            data / "assets",
            "user_files",
            "project",
            "never_auto_clean",
            "Uploaded/source media and previews; never treat as disposable cache.",
        ),
        PathSpec(
            "project_exports",
            data / "exports",
            "user_output",
            "project",
            "preserve",
            "User-requested evidence exports; not a cache.",
        ),
        PathSpec(
            "project_logs",
            data / "logs",
            "runtime_output",
            "project",
            "preserve",
            "Service and diagnostic logs; useful for recovery and not a RAM cache.",
        ),
        PathSpec(
            "project_database",
            data / "neuroloop.db",
            "runtime_state",
            "project",
            "never_auto_clean",
            "SQLite queue, run, and evaluation state.",
        ),
        PathSpec(
            "execution_quarantine",
            data / "inference-quarantine.json",
            "runtime_state",
            "project",
            "never_modify",
            "Safety hold; this audit never clears, edits, or bypasses it.",
        ),
        PathSpec(
            "project_runtimes",
            root / ".runtimes",
            "runtime_environment",
            "project",
            "preserve",
            "Pinned Python environments and installed dependencies; not a disposable cache.",
            scan=False,
        ),
        PathSpec(
            "model_weights",
            root / "models",
            "model_weights",
            "project",
            "never_delete",
            "Downloaded model weights and readout assets; model files are intentionally ignored by Git.",
            scan=False,
        ),
        PathSpec(
            "tribe_weights",
            root / "tribev2-balanced-qv-local",
            "model_weights_and_runtime",
            "project",
            "never_delete",
            "Original checkpoint, quantized weights, and runtime files; never use as a RAM cleanup target.",
            scan=False,
        ),
        PathSpec(
            "uv_user_cache",
            uv_cache,
            "disk_cache",
            "user",
            "package_scoped_manual_review_only",
            "uv download/build/index cache. It is disk-only; package-scoped cleanup can force later downloads.",
        ),
    ]


def file_size(path: Path) -> int | None:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return scan_tree(path, DEFAULT_MAX_ENTRIES)["bytes"]
    except OSError:
        return None
    return None


def candidate(path: Path, root: Path, candidate_id: str, reason: str, preconditions: Iterable[str]) -> dict[str, Any]:
    path = absolute(path)
    size = file_size(path)
    return {
        "candidate_id": candidate_id,
        "path": str(path),
        "relative_path": display_path(path, root),
        "exists": path.exists(),
        "bytes": size,
        "human_size": human_bytes(size),
        "classification": "manual_review_candidate",
        "proposed_scope": "this exact path only",
        "automatic_action": "none",
        "preconditions": list(preconditions),
        "reason": reason,
    }


def collect_allowlist(root: Path, inventory: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = {item["key"]: item for item in inventory}
    allowlist: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    tmp = root / "data" / "tmp"
    if tmp.is_dir():
        try:
            children = sorted(tmp.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            children = []
        for child in children:
            if child.is_dir() and child.name.startswith("neuroloop-tests-"):
                allowlist.append(
                    candidate(
                        child,
                        root,
                        "test-scratch",
                        "Test fixture scratch directory; it is not needed by a running application after the test process exits.",
                        (
                            "confirm no pytest or verification process references this directory",
                            "confirm the directory is not needed for a failure investigation",
                            "remove only this exact test-scratch directory manually, if approved",
                        ),
                    )
                )

    results = root / "data" / "results"
    if results.is_dir():
        try:
            result_dirs = sorted(results.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            result_dirs = []
        for result_dir in result_dirs:
            if not result_dir.is_dir():
                continue
            # Restrict the artifact allowlist to the application's own result
            # key shape or a clearly named local smoke result.
            if not (RESULT_KEY.fullmatch(result_dir.name) or result_dir.name.startswith("mac-mps-")):
                continue
            has_evidence = (result_dir / "evidence.json").is_file()
            has_failure = (result_dir / "process-error.json").is_file()
            if not (has_failure or not has_evidence):
                continue
            for name in sorted(EPHEMERAL_RESULT_NAMES):
                path = result_dir / name
                if path.is_file():
                    allowlist.append(
                        candidate(
                            path,
                            root,
                            "interrupted-evaluator-media",
                            "Evaluator-owned intermediate media left by an incomplete result; the normal evaluator finally block attempts to remove it.",
                            (
                                "confirm the result is failed/incomplete and no evaluator process is active",
                                "retain process-error.json, evidence.json, prediction.npy, and segments.json",
                                "remove only this exact intermediate file manually, if approved",
                            ),
                        )
                    )
            tsam = result_dir / "tsam"
            if tsam.is_dir():
                allowlist.append(
                    candidate(
                        tsam,
                        root,
                        "interrupted-tsam-temporary",
                        "TSAM frame/audio scratch directory under an incomplete evaluator result.",
                        (
                            "confirm the result is failed/incomplete and no evaluator process is active",
                            "retain the parent result receipt and any required evidence before cleanup",
                            "remove only this exact tsam directory manually, if approved",
                        ),
                    )
                )

    feature_cache = root / "cache"
    if feature_cache.is_dir():
        try:
            children = sorted(feature_cache.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            children = []
        for child in children:
            if child.is_dir() and child.name.startswith("tribe-local-"):
                exclusions.append(
                    {
                        "path": str(child),
                        "relative_path": display_path(child, root),
                        "classification": "not_a_RAM_cleanup_candidate",
                        "reason": "Deleting a feature cache removes reusable disk features and can increase cold-start work; it does not release tensors already resident in a live MPS process.",
                        "automatic_action": "none",
                    }
                )

    uv = by_key.get("uv_user_cache")
    if uv and uv.get("exists"):
        allowlist.append(
            {
                "candidate_id": "uv-package-scope",
                "path": uv["path"],
                "relative_path": uv["relative_path"],
                "exists": True,
                "bytes": uv.get("bytes"),
                "human_size": uv.get("human_size"),
                "classification": "manual_review_candidate",
                "proposed_scope": "one explicitly selected uv package/cache entry, never the whole cache",
                "automatic_action": "none",
                "preconditions": [
                    "inspect which package/cache entry is stale and confirm no uv install/build is active",
                    "use uv's package-scoped cleanup only after confirming the locked environments remain reproducible",
                    "expect future installs to redownload removed artifacts",
                ],
                "reason": "The host's uv cache is a user-level disk cache; it is not live RAM and broad cleaning is not justified by this audit.",
            }
        )

    return allowlist, exclusions


def memory_snapshot() -> dict[str, Any]:
    """Read host memory only; MPS allocator counters are intentionally absent."""

    snapshot: dict[str, Any] = {
        "classification": "live_ram",
        "source": "optional_psutil_or_os_sysconf",
        "mps_native_allocated_bytes": None,
        "note": "This is host live-memory telemetry, not a disk-cache size and not an MPS allocator measurement.",
    }
    try:
        import psutil  # type: ignore[import-not-found]

        memory = psutil.virtual_memory()
        snapshot.update(
            {
                "source": "psutil.virtual_memory",
                "total_bytes": int(memory.total),
                "available_bytes": int(memory.available),
                "used_bytes": int(memory.used),
                "human_total": human_bytes(int(memory.total)),
                "human_available": human_bytes(int(memory.available)),
            }
        )
        return snapshot
    except (ImportError, OSError, AttributeError):
        pass

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        total = page_size * pages
        snapshot.update({"total_bytes": total, "human_total": human_bytes(total), "available_bytes": None, "human_available": "unknown"})
    except (OSError, ValueError, TypeError):
        snapshot.update({"total_bytes": None, "human_total": "unknown", "available_bytes": None, "human_available": "unknown"})

    return snapshot


def process_rss_snapshot() -> dict[str, Any]:
    """Report this audit process's peak RSS without inspecting or altering others."""

    try:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform != "darwin":
            value *= 1024
        return {"current_audit_process_max_rss_bytes": value, "human_size": human_bytes(value)}
    except (AttributeError, OSError, ValueError):
        return {"current_audit_process_max_rss_bytes": None, "human_size": "unknown"}


def uv_observation(uv_path: Path, source: str, inventory: list[dict[str, Any]]) -> dict[str, Any]:
    item = next((record for record in inventory if record["key"] == "uv_user_cache"), None)
    return {
        "path": str(uv_path),
        "path_resolution": source,
        "exists": bool(item and item.get("exists")),
        "bytes": item.get("bytes") if item else None,
        "human_size": item.get("human_size") if item else "missing",
        "cleanup_result": "not_run",
        "note": "This audit does not invoke uv cache clean. The caller must choose any package-scoped cleanup manually; no broad cleanup is implied.",
    }


def build_report(root: Path, max_entries: int) -> dict[str, Any]:
    root = absolute(root).resolve()
    uv_path, uv_source = configured_uv_cache()
    specs = path_specs(root)
    inventory = [describe(spec, root, max_entries) for spec in specs]
    allowlist, exclusions = collect_allowlist(root, inventory)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "root": str(root),
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "read_only": {
            "mode": "report_and_dry_run",
            "writes_performed": [],
            "deletions_performed": [],
            "renames_performed": [],
            "processes_started": [],
            "models_started": [],
            "services_changed": [],
            "quarantine_changed": False,
            "allowlist_is_advisory": True,
        },
        "memory": {**memory_snapshot(), **process_rss_snapshot()},
        "inventory": inventory,
        "allowlist": allowlist,
        "excluded_from_cleanup": exclusions,
        "uv": uv_observation(uv_path, uv_source, inventory),
        "interpretation": [
            "Disk-cache bytes are not live RAM bytes. A feature cache is read later by an evaluator and is not the same object as tensors resident in an active MPS process.",
            "Deleting a feature cache can reduce disk usage and may remove reusable intermediates, but it does not guarantee a lower cold-start or peak unified-memory requirement.",
            "Model weights, runtime environments, user media, database state, logs, exports, and the execution quarantine are not cleanup candidates.",
            "MPS native allocator counters are intentionally not collected by this dependency-free audit; use the guarded profiler for a separately approved model measurement.",
        ],
    }


def print_human(report: dict[str, Any], dry_run: bool) -> None:
    print("NeuroLoop cache audit (read-only)")
    print(f"root: {report['root']}")
    print(f"host: {report['host']['system']} {report['host']['machine']}")
    memory = report["memory"]
    print(f"live RAM available: {memory.get('human_available', 'unknown')} (source: {memory.get('source')})")
    print("disk inventory:")
    for item in report["inventory"]:
        size = item.get("human_size", "unknown")
        state = "present" if item.get("exists") else "missing"
        print(f"  {item['key']}: {state}, {size}, {item['retention_policy']}")
    print(f"manual-review allowlist ({'dry-run' if dry_run else 'report'}; no actions):")
    if report["allowlist"]:
        for item in report["allowlist"]:
            print(f"  {item['candidate_id']}: {item['path']} ({item['human_size']})")
    else:
        print("  none found")
    print("read-only mutations: none")


def self_test() -> int:
    """Check the source's read-only contract without touching project paths."""

    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {"subprocess", "torch", "numpy", "pandas"}
    forbidden_calls = {"unlink", "rmtree", "remove", "write_text", "write_bytes", "rename", "mkdir"}
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name.split(".", 1)[0] in forbidden_imports:
                    violations.append(f"import {item.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".", 1)[0] in forbidden_imports:
            violations.append(f"from {node.module}")
        elif isinstance(node, ast.Call):
            function = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
            if function in forbidden_calls:
                violations.append(f"call {function}")
    if violations:
        print(json.dumps({"passed": False, "violations": violations}, sort_keys=True))
        return 1
    print(json.dumps({"passed": True, "contract": "read-only inventory and advisory allowlist"}, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Inventory NeuroLoop disk caches and live-RAM context without deleting anything.")
    command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="NeuroLoop checkout to inspect")
    command.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES, help="Maximum recursive entries per scanned directory")
    command.add_argument("--dry-run", action="store_true", help="Emit the advisory cleanup allowlist; still performs no mutation")
    command.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    command.add_argument("--self-test", action="store_true", help="Check the read-only implementation contract")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.self_test:
        return self_test()
    if args.max_entries < 1:
        parser().error("--max-entries must be positive")
    report = build_report(args.root, args.max_entries)
    if args.json:
        print(json.dumps({**report, "dry_run_requested": args.dry_run}, indent=2, sort_keys=True))
    else:
        print_human(report, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
