"""Local MCP transport for Codex. Uses the same domain services and durable queue.

Start NeuroLoop before scheduling model work. Only MCP protocol messages go to stdout.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Match Start-NeuroLoop.sh on Apple Silicon so stdio and HTTP MCP enforce the
# same local execution policy. The preserved Windows quarantine remains active
# everywhere else, and the worker still enforces RAM/headroom checks.
if sys.platform == 'darwin':
    os.environ.setdefault('NEUROLOOP_INFERENCE_DEVICE', 'mps')
    os.environ.setdefault('NEUROLOOP_ALLOW_MPS_INFERENCE', 'true')
    os.environ.setdefault('NEUROLOOP_MPS_MEMORY_RESERVE_GIB', '1.5')
    os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')
sys.path.insert(0, str(ROOT / 'backend'))
from neuroloop.db import initialize
from neuroloop.mcp_server import mcp

if __name__ == '__main__':
    initialize()
    mcp.run(transport='stdio')
