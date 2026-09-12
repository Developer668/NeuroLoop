"""Read-only process/RAM/GPU profiler for an explicitly running NeuroLoop job.

This tool never imports NeuroLoop, PyTorch, a model loader, or a database module,
and it never starts, stops, signals, or attaches to a process.  Give it the PID
of an already approved supervisor (or a services.json state file) and it records
the process tree plus host telemetry until the bounded observation window ends.
It is intended to be run beside, not instead of, the existing run guard.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


GIB = 1024**3
MAX_DURATION_SECONDS = 1800.0
MAX_INTERVAL_SECONDS = 60.0


def _run_read_only(command: list[str], timeout: float = 5.0) -> str | None:
    """Return bounded command output, or ``None`` when the probe is unavailable."""

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def _memory_from_psutil() -> dict[str, Any] | None:
    try:
        import psutil  # type: ignore
    except ImportError:
        return None
    try:
        value = psutil.virtual_memory()
    except (OSError, RuntimeError):
        return None
    return {
        "ram_total_bytes": int(value.total),
        "ram_available_bytes": int(value.available),
        "source": "psutil.virtual_memory",
    }


def _memory_from_procfs() -> dict[str, Any] | None:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None
    values: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name, _, raw = line.partition(":")
            number = raw.strip().split()[0]
            values[name] = int(number) * 1024
    except (OSError, ValueError, IndexError):
        return None
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None or available is None:
        return None
    return {
        "ram_total_bytes": total,
        "ram_available_bytes": available,
        "source": "/proc/meminfo",
    }


def _memory_from_macos() -> dict[str, Any] | None:
    total_text = _run_read_only(["sysctl", "-n", "hw.memsize"])
    vm_text = _run_read_only(["vm_stat"])
    if not total_text or not vm_text:
        return None
    try:
        total = int(total_text)
        page_size = 4096
        page_line = next(
            line for line in vm_text.splitlines() if "page size of" in line
        )
        page_size = int(page_line.split("page size of", 1)[1].split("bytes", 1)[0].strip())
        pages: dict[str, int] = {}
        for line in vm_text.splitlines():
            if ":" not in line:
                continue
            name, raw = line.split(":", 1)
            number = raw.strip().rstrip(".")
            if number.isdigit():
                pages[name.strip()] = int(number)
        # This is deliberately labelled an estimate.  macOS's compressed and
        # purgeable accounting is not equivalent to psutil's available value.
        available_pages = sum(
            pages.get(name, 0)
            for name in (
                "Pages free",
                "Pages inactive",
                "Pages speculative",
                "Pages purgeable",
            )
        )
        return {
            "ram_total_bytes": total,
            "ram_available_bytes": available_pages * page_size,
            "source": "vm_stat_estimate",
            "available_is_estimate": True,
        }
    except (ValueError, StopIteration):
        return None


def host_memory() -> dict[str, Any]:
    """Read system memory without importing a model runtime."""

    for probe in (_memory_from_psutil, _memory_from_procfs):
        result = probe()
        if result is not None:
            return result
    if sys.platform == "darwin":
        result = _memory_from_macos()
        if result is not None:
            return result
    return {
        "ram_total_bytes": None,
        "ram_available_bytes": None,
        "source": "unavailable",
    }


def _psutil_process_rows(root_pid: int) -> list[dict[str, Any]] | None:
    try:
        import psutil  # type: ignore
    except ImportError:
        return None
    try:
        root = psutil.Process(root_pid)
        processes = [root, *root.children(recursive=True)]
    except (psutil.Error, OSError, ValueError):
        return []

    rows: list[dict[str, Any]] = []
    for process in processes:
        try:
            memory = process.memory_info()
            rows.append(
                {
                    "pid": int(process.pid),
                    "ppid": int(process.ppid()),
                    "name": process.name(),
                    "status": process.status(),
                    "rss_bytes": int(memory.rss),
                    "command": " ".join(process.cmdline()),
                }
            )
        except (psutil.Error, OSError, ValueError):
            continue
    return rows


def _ps_process_rows(root_pid: int) -> list[dict[str, Any]]:
    output = _run_read_only(
        ["ps", "-axo", "pid=,ppid=,state=,rss=,command="], timeout=5.0
    )
    if output is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.strip().split(None, 4)
        if len(fields) < 5:
            continue
        try:
            rows.append(
                {
                    "pid": int(fields[0]),
                    "ppid": int(fields[1]),
                    "status": fields[2],
                    "rss_bytes": int(fields[3]) * 1024,
                    "command": fields[4],
                }
            )
        except ValueError:
            continue
    return rows


def process_rows(root_pid: int) -> list[dict[str, Any]]:
    """Return the root and descendants, without changing process state."""

    rows = _psutil_process_rows(root_pid)
    if rows is None:
        rows = _ps_process_rows(root_pid)
    if not rows:
        return []

    by_parent: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_parent.setdefault(int(row["ppid"]), []).append(row)
    selected: list[dict[str, Any]] = []
    pending = [root_pid]
    seen: set[int] = set()
    while pending:
        parent = pending.pop()
        if parent in seen:
            continue
        seen.add(parent)
        for row in rows:
            if int(row["pid"]) == parent:
                selected.append(row)
        pending.extend(int(row["pid"]) for row in by_parent.get(parent, []))
    return sorted(selected, key=lambda row: int(row["pid"]))


def cuda_probe() -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    output = _run_read_only(
        [
            executable,
            "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=5.0,
    )
    if not output:
        return {"backend": "cuda", "telemetry": "unavailable"}
    fields = [field.strip() for field in output.splitlines()[0].split(",")]
    if len(fields) != 7:
        return {"backend": "cuda", "telemetry": "unparseable"}
    try:
        return {
            "backend": "cuda",
            "name": fields[0],
            "driver": fields[1],
            "total_mib": float(fields[2]),
            "used_mib": float(fields[3]),
            "free_mib": float(fields[4]),
            "temperature_c": float(fields[5]),
            "utilization_percent": float(fields[6]),
            "source": "nvidia-smi",
        }
    except ValueError:
        return {"backend": "cuda", "telemetry": "unparseable"}


def accelerator_probe() -> dict[str, Any]:
    cuda = cuda_probe()
    if cuda is not None:
        return cuda
    if sys.platform == "darwin":
        # MPS is unified memory.  Native allocator counters are process-local
        # and cannot be queried for another PID without instrumenting that
        # process; this profiler intentionally does not import torch to do so.
        return {
            "backend": "mps",
            "native_allocated_bytes": None,
            "native_reserved_bytes": None,
            "native_counters_source": "not_observable_externally",
            "note": "Use process RSS and host available RAM as the external MPS proxy.",
        }
    return {"backend": "unknown", "telemetry": "no nvidia-smi; MPS not applicable"}


def sample(root_pid: int, started: float) -> dict[str, Any]:
    rows = process_rows(root_pid)
    rss_values = [int(row.get("rss_bytes", 0)) for row in rows]
    memory = host_memory()
    return {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "system": memory,
        "accelerator": accelerator_probe(),
        "processes": rows,
        "process_metrics": {
            "count": len(rows),
            "rss_sum_bytes": sum(rss_values),
            "rss_max_bytes": max(rss_values, default=0),
            "root_seen": any(int(row["pid"]) == root_pid for row in rows),
        },
    }


def summarize_samples(samples: list[dict[str, Any]], requested_seconds: float) -> dict[str, Any]:
    available = [
        int(item["system"]["ram_available_bytes"])
        for item in samples
        if item["system"].get("ram_available_bytes") is not None
    ]
    rss_sum = [int(item["process_metrics"]["rss_sum_bytes"]) for item in samples]
    rss_max = [int(item["process_metrics"]["rss_max_bytes"]) for item in samples]
    counts = [int(item["process_metrics"]["count"]) for item in samples]
    accelerator_backends = sorted(
        {item["accelerator"].get("backend", "unknown") for item in samples}
    )
    cuda_free = [
        float(item["accelerator"]["free_mib"])
        for item in samples
        if item["accelerator"].get("backend") == "cuda"
        and item["accelerator"].get("free_mib") is not None
    ]
    cuda_used = [
        float(item["accelerator"]["used_mib"])
        for item in samples
        if item["accelerator"].get("backend") == "cuda"
        and item["accelerator"].get("used_mib") is not None
    ]
    return {
        "requested_seconds": requested_seconds,
        "sample_count": len(samples),
        "elapsed_seconds": samples[-1]["elapsed_seconds"] if samples else 0.0,
        "accelerator_backends": accelerator_backends,
        "ram_available_min_bytes": min(available) if available else None,
        "process_rss_sum_peak_bytes": max(rss_sum, default=0),
        "process_rss_max_peak_bytes": max(rss_max, default=0),
        "process_count_max": max(counts, default=0),
        "cuda_free_min_mib": min(cuda_free) if cuda_free else None,
        "cuda_used_peak_mib": max(cuda_used, default=None),
        "mps_native_memory_observed": any(
            item["accelerator"].get("native_allocated_bytes") is not None
            for item in samples
        ),
        "interpretation": (
            "Process RSS and host available RAM are external proxies. "
            "They do not replace in-process PyTorch CUDA peak counters or a native MPS allocator trace."
        ),
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".partial", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_pid(state_file: Path) -> int:
    value = json.loads(state_file.read_text(encoding="utf-8"))
    pid = value.get("pid")
    if type(pid) is not int or pid <= 0:
        raise ValueError(f"State file does not contain a positive integer pid: {state_file}")
    return pid


def self_test() -> int:
    synthetic = [
        {
            "elapsed_seconds": 0.0,
            "system": {"ram_available_bytes": 4 * GIB},
            "accelerator": {"backend": "mps", "native_allocated_bytes": None},
            "process_metrics": {"count": 2, "rss_sum_bytes": 100, "rss_max_bytes": 70},
        },
        {
            "elapsed_seconds": 1.0,
            "system": {"ram_available_bytes": 2 * GIB},
            "accelerator": {"backend": "mps", "native_allocated_bytes": None},
            "process_metrics": {"count": 3, "rss_sum_bytes": 180, "rss_max_bytes": 120},
        },
    ]
    result = summarize_samples(synthetic, 1.0)
    assert result["ram_available_min_bytes"] == 2 * GIB
    assert result["process_rss_sum_peak_bytes"] == 180
    assert result["process_count_max"] == 3
    assert result["mps_native_memory_observed"] is False
    print(json.dumps({"passed": True, "model_imported": False, "scope": "pure profiler self-test"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Test aggregation without reading a process or loading a model")
    parser.add_argument("--pid", type=int, help="PID of an already-running approved supervisor")
    parser.add_argument("--state-file", type=Path, help="Read the supervisor PID from a services.json file")
    parser.add_argument("--duration", type=float, default=60.0, help="Observation bound in seconds (maximum 1800)")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples (maximum 60)")
    parser.add_argument("--label", default="real-loop", help="Evidence label")
    parser.add_argument("--output", type=Path, help="JSON output path")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if (args.pid is None) == (args.state_file is None):
        parser.error("provide exactly one of --pid or --state-file")
    if args.output is None:
        parser.error("--output is required unless --self-test is used")
    if type(args.pid) is int and args.pid <= 0:
        parser.error("--pid must be positive")
    if not 0 < args.duration <= MAX_DURATION_SECONDS:
        parser.error(f"--duration must be in (0, {MAX_DURATION_SECONDS:g}]")
    if not 0 < args.interval <= MAX_INTERVAL_SECONDS:
        parser.error(f"--interval must be in (0, {MAX_INTERVAL_SECONDS:g}]")

    root_pid = args.pid if args.pid is not None else load_pid(args.state_file)
    started = time.monotonic()
    report: dict[str, Any] = {
        "version": 1,
        "label": args.label,
        "root_pid": root_pid,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host": {"system": platform.system(), "machine": platform.machine()},
        "safety": {
            "models_imported": False,
            "processes_started": False,
            "processes_signalled": False,
            "quarantine_changed": False,
        },
        "samples": [],
    }
    while True:
        current = sample(root_pid, started)
        report["samples"].append(current)
        if current["elapsed_seconds"] >= args.duration:
            break
        remaining = args.duration - current["elapsed_seconds"]
        time.sleep(min(args.interval, max(0.0, remaining)))
    report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["summary"] = summarize_samples(report["samples"], args.duration)
    atomic_write(args.output, report)
    print(
        json.dumps(
            {
                "label": args.label,
                "root_pid": root_pid,
                "samples": len(report["samples"]),
                "ram_available_min_bytes": report["summary"]["ram_available_min_bytes"],
                "process_rss_sum_peak_bytes": report["summary"]["process_rss_sum_peak_bytes"],
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
