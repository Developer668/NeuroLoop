"""Install the isolated partner runtimes without running model inference."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=ROOT)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This setup targets Windows; see PARTNER-START-HERE.md.")
    for tool in ("uv", "npm.cmd"):
        if not shutil.which(tool):
            raise SystemExit(f"Install {tool} first; see PARTNER-START-HERE.md.")

    for name in ("app", "model", "wandb-mcp"):
        python = ROOT / ".runtimes" / name / "Scripts" / "python.exe"
        if not python.exists():
            run("uv", "venv", str(python.parents[1]), "--python", "3.11.9")
        sync = [
            "uv",
            "pip",
            "sync",
            f"infrastructure/runtime/{name}.lock",
            "--python",
            str(python),
        ]
        if name == "model":
            sync += ["--torch-backend", "cu128"]
        run(*sync)
        run("uv", "pip", "check", "--python", str(python))

    config = ROOT / ".env"
    if not config.exists():
        config.write_text(
            "NEUROLOOP_AUTH_TOKEN="
            + secrets.token_urlsafe(48)
            + "\nNEUROLOOP_WEAVE_ENABLED=false\n"
            "NEUROLOOP_PLANNER_ENABLED=false\nNEUROLOOP_TSAM_ENABLED=false\n",
            encoding="utf-8",
        )
    (ROOT / ".runtimes" / "active.json").write_text(
        json.dumps({"version": 1, "app": "app", "model": "model"}),
        encoding="utf-8",
    )
    subprocess.run(["npm.cmd", "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run(["npm.cmd", "run", "build"], cwd=ROOT / "frontend", check=True)
    print("Dependencies and frontend build completed. Open Start-NeuroLoop.cmd.")
    print("GPU work remains held until the execution hold is explicitly resolved.")


if __name__ == "__main__":
    main()
