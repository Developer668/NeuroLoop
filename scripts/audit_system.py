"""Self-contained release audit for the local NeuroLoop stack.

Creates its own tiny technical fixture, uses the authenticated HTTP + MCP surfaces,
runs one bounded response-target loop, and verifies stored evidence. No sponsor API,
external network access, or synthetic neural fallback is used.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import platform
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/verification/release" / os.getenv("NEUROLOOP_AUDIT_NAME", "runtime-audit")
if not OUT.resolve().is_relative_to(ROOT / "data/verification/release"):
    raise ValueError("Audit output must stay within release verification")
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "backend"))
from neuroloop.readout import summarize  # noqa: E402


def make_fixture(path: Path) -> None:
    image = Image.new("RGB", (640, 360), (28, 45, 58))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 80, 570, 280), outline=(196, 222, 211), width=8)
    draw.ellipse((255, 105, 385, 235), fill=(229, 189, 91))
    image.save(path, "PNG")


async def main() -> None:
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "calls": [],
        "failures": [],
        "scope": "Local technical release audit only; no human-response validity claim.",
    }

    def save() -> None:
        (OUT / "runtime.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def check(name: str, value: bool) -> None:
        report["checks"][name] = bool(value)
        if not value:
            report["failures"].append(name)
        save()

    fixture = OUT / "technical-audit-source.png"
    make_fixture(fixture)

    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=60) as http:
        check("unauthenticated_api_rejected", http.get("/api/dashboard").status_code == 401)
        check("unauthenticated_mcp_rejected", http.post("/mcp/", json={}).status_code == 401)
        check(
            "cross_origin_session_rejected",
            http.post(
                "/auth/local",
                headers={"Origin": "https://example.invalid", "X-NeuroLoop-Local": "browser"},
            ).status_code
            == 403,
        )
        auth = http.post(
            "/auth/local",
            headers={"Origin": "http://localhost:3010", "X-NeuroLoop-Local": "browser"},
        )
        auth.raise_for_status()
        headers = {"Authorization": "Bearer " + auth.json()["token"]}
        http.headers.update(headers)

        with fixture.open("rb") as handle:
            uploaded_response = http.post(
                "/api/assets", files={"file": (fixture.name, handle, "image/png")}
            )
        uploaded_response.raise_for_status()
        uploaded = uploaded_response.json()
        report["fixture_asset_id"] = uploaded["id"]

        async with httpx.AsyncClient(headers=headers, timeout=60) as client:
            async with streamable_http_client(
                "http://127.0.0.1:8010/mcp/", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    http_tools = [t.name for t in (await session.list_tools()).tools]
                    report["http_tools"] = http_tools
                    response = await session.call_tool("get_capabilities", {})
                    check("http_mcp_real_capabilities", not response.isError)

        app_python = ROOT / ".runtimes/app" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        server = StdioServerParameters(
            command=str(app_python), args=[str(ROOT / "scripts/mcp_stdio.py")], cwd=str(ROOT)
        )
        with (OUT / "mcp-stderr.log").open("w", encoding="utf-8") as errors:
            async with stdio_client(server, errlog=errors) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    stdio_tools = [t.name for t in (await session.list_tools()).tools]
                    report["stdio_tools"] = stdio_tools
                    required_tools = {
                        "get_capabilities",
                        "list_workspace",
                        "create_project",
                        "render_creative",
                        "optimize_response",
                        "get_run",
                        "cancel_run",
                        "get_evidence",
                        "export_result",
                    }
                    check(
                        "mcp_transports_match_and_core_tools_exist",
                        set(stdio_tools) == set(http_tools)
                        and required_tools.issubset(stdio_tools),
                    )
                    report["mcp_tool_count"] = len(stdio_tools)

                    async def call(name: str, args: dict | None = None) -> dict:
                        result = await session.call_tool(name, args or {})
                        if result.isError:
                            raise RuntimeError(name + ": " + str(result.content))
                        report["calls"].append(name)
                        return result.structuredContent or json.loads(result.content[0].text)

                    report["hardware_before"] = await call("get_system_status")
                    capabilities = await call("get_capabilities")
                    report["capabilities"] = capabilities
                    check("tribe_ready", capabilities["tribe"]["status"] == "weights_present")
                    check(
                        "kragel_ready",
                        capabilities["kragel"]["status"] == "experimental_ready",
                    )
                    check(
                        "tsam_assets_ready",
                        capabilities["tsam"]["status"] == "experimental_weights_present",
                    )
                    check(
                        "sponsor_generation_still_gated",
                        all(
                            p["status"] == "awaiting_sponsor_access"
                            for p in capabilities["generation_providers"]
                        ),
                    )

                    rendered = await call(
                        "render_creative",
                        {
                            "asset_id": uploaded["id"],
                            "headline": "NeuroLoop release audit",
                            "subline": "Local technical fixture",
                            "duration": 6,
                        },
                    )
                    project = await call(
                        "create_project",
                        {
                            "name": "System audit / response loop",
                            "brief": "Technical integration fixture only. Preserve duration and validate the local response loop.",
                            "asset_id": rendered["id"],
                        },
                    )
                    # Apple MPS is materially slower than CUDA for the current V-JEPA2
                    # feature path. Keep the same two-evaluation bound, but give the
                    # real model enough wall time to finish rather than treating a
                    # platform-speed difference as an integration failure.
                    audit_seconds = 2400 if platform.system() == "Darwin" else 900
                    run = await call(
                        "optimize_response",
                        {
                            "project_id": project["id"],
                            "emotion_targets": {"happiness": 0.8, "surprise": 0.6},
                            "max_evaluations": 2,
                            "max_seconds": audit_seconds,
                            "min_gain": 0.0001,
                            "no_speech": True,
                            "include_tsam": False,
                            "include_kragel": True,
                        },
                    )
                    report["fresh_project_id"] = project["id"]
                    report["fresh_run_id"] = run["id"]
                    save()

                    deadline = time.monotonic() + audit_seconds + 60
                    stage = ""
                    while time.monotonic() < deadline:
                        run = await call("get_run", {"run_id": run["id"]})
                        if run["stage"] != stage:
                            stage = run["stage"]
                            print(stage, flush=True)
                        if run["status"] not in {"queued", "running"}:
                            break
                        await asyncio.sleep(3)
                    else:
                        raise TimeoutError("Fresh response loop did not finish within the audit limit")

                    report["fresh_run"] = run
                    completed = run["status"] == "completed"
                    check("fresh_response_loop_completed", completed)
                    if not completed:
                        raise RuntimeError(run.get("error") or run["stage"])
                    check("bounded_evaluation_count", 1 <= run["evaluations_used"] <= 2)
                    check(
                        "response_objective_used",
                        run["result"].get("metric") == "response-target-distance/v1",
                    )

                    identity = run["result"]["best_evaluation_id"]
                    evidence = await call("get_evidence", {"evaluation_id": identity})
                    report["fresh_evidence"] = evidence
                    check("real_tribe_shape", evidence["evidence"].get("shape", [0, 0])[-1] == 20484)
                    kragel = evidence["evidence"].get("kragel", {})
                    check("kragel_bridge_executed", kragel.get("status") == "experimental")
                    response_report = evidence["evidence"].get("response_ensemble", {})
                    check(
                        "response_ensemble_uses_kragel",
                        "kragel" in response_report.get("active_sources", []),
                    )

                    exported = await call("export_result", {"run_id": run["id"]})
                    archive = http.get(exported["archive_path"])
                    archive.raise_for_status()
                    (OUT / "fresh-output.zip").write_bytes(archive.content)
                    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
                        check("export_zip_integrity", bundle.testzip() is None)
                        report["export_members"] = bundle.namelist()
                    ledger = await call("get_research_ledger")
                    check(
                        "new_result_visible_in_research",
                        any(e["id"] == identity for e in ledger["evaluations"]),
                    )

        report["arrays"] = []
        report["assets"] = []
        with sqlite3.connect(
            "file:" + str(ROOT / "data/neuroloop.db") + "?mode=ro", uri=True
        ) as db:
            db.row_factory = sqlite3.Row
            report["database_integrity"] = db.execute("pragma integrity_check").fetchone()[0]
            for row in db.execute("select * from evaluations"):
                try:
                    path = Path(row["prediction_path"])
                    x = np.load(path, allow_pickle=False)
                    stored = json.loads(row["evidence"])
                    computed = summarize(x, stored["times"])
                    matched = all(
                        np.allclose(computed[k], stored[k], atol=1e-7)
                        for k in ["left_mean", "right_mean", "rms", "range"]
                    )
                    frame = http.get("/api/evaluations/" + row["id"] + "/frame?index=0")
                    frame.raise_for_status()
                    served = np.array_equal(np.asarray(frame.json()["values"]), x[0])
                    report["arrays"].append(
                        {
                            "id": row["id"],
                            "shape": list(x.shape),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "summary_matches": matched,
                            "api_frame_exact": served,
                            "finite": bool(np.isfinite(x).all()),
                            "nonconstant": bool(np.ptp(x) > 0),
                        }
                    )
                except Exception as exc:
                    report["failures"].append("array " + row["id"] + ": " + str(exc))
            for row in db.execute("select id,path,sha256 from assets"):
                path = Path(row["path"])
                actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                report["assets"].append({"id": row["id"], "hash_matches": actual == row["sha256"]})
            report["active_jobs"] = db.execute(
                "select count(*) from runs where status in ('queued','running')"
            ).fetchone()[0]
            report["run_status_counts"] = dict(
                db.execute("select status,count(*) from runs group by status")
            )

        check(
            "all_stored_arrays_match_summaries_and_served_frames",
            bool(report["arrays"])
            and all(
                all(e[k] for k in ["summary_matches", "api_frame_exact", "finite", "nonconstant"])
                for e in report["arrays"]
            ),
        )
        check("all_managed_asset_hashes_match", all(a["hash_matches"] for a in report["assets"]))
        check(
            "database_integrity_and_idle_queue",
            report["database_integrity"] == "ok" and report["active_jobs"] == 0,
        )
        report["connections"] = http.post("/api/connections/check").json()

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["passed"] = not report["failures"] and all(report["checks"].values())
    report["calls"] = sorted(set(report["calls"]))
    save()
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "checks": report["checks"],
                "array_count": len(report["arrays"]),
                "asset_count": len(report["assets"]),
                "fresh_run_id": report["fresh_run_id"],
                "failures": report["failures"],
            },
            indent=2,
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
