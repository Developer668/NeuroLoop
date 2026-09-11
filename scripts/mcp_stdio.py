"""Local MCP transport for Codex. Uses the same domain services and durable queue.

Start NeuroLoop before scheduling model work. Only MCP protocol messages go to stdout.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from neuroloop.db import initialize
from neuroloop.mcp_server import mcp

if __name__ == '__main__':
    initialize()
    mcp.run(transport='stdio')
