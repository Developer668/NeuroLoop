# Local agent and service connections

Two MCP servers are configured in Codex. Their exact stdio commands were initialized using the real MCP SDK; configuration does not retroactively load tools into an already-running conversation. Reload MCP connections or reopen the client to discover them.

```powershell
codex mcp get neuroloop
codex mcp get wandb
```

| Server | Command | Current behavior |
|---|---|---|
| neuroloop | `D:\NeuroLoop\.runtimes\app\Scripts\python.exe D:\NeuroLoop\scripts\mcp_stdio.py` | 18 tools sharing the actual local database, services and bounded queue |
| wandb | `D:\NeuroLoop\.runtimes\wandb-mcp\Scripts\python.exe D:\NeuroLoop\scripts\wandb_mcp.py` | Official W&B MCP 0.3.7, 19 read-only tools; real remote trace query verified |

W&B credentials load privately from `.env`. The wrapper enables read-only tools and disables agent mutation tools. No API key is copied into the Codex MCP command.

## Other local clients

Authenticated HTTP: `http://127.0.0.1:8010/mcp/`. Open **MCP connections → Test MCP connection** to initialize a real session and discover schemas. **Download client config** creates an eight-hour bearer token for compatible clients. Keep it private. Stdio clients on this computer can use the exact command above and inherit local filesystem trust.

The current crash hold blocks model work from the website, API, MCP and Launch. Reading status, saved evidence and the research ledger remains available. No alternate MCP route bypasses the shared domain guard.

## Verification

```powershell
.\.runtimes\app\Scripts\python.exe scripts/verify_recovery.py
.\.runtimes\app\Scripts\python.exe scripts/verify_wandb_mcp.py
```

The first script uses real HTTP and stdio sessions, reads current data, verifies the held queue rejects work, recomputes saved outputs and checks auth/session revocation. It does not perform inference. The second discovers W&B tools and queries actual remote traces. Receipts are in `data/verification/release/recovery-audit.json` and `wandb-mcp-schema.json`.

**Check service connections** reports current HTTP/auth/heartbeat state separately from installed files and remote receipts. marimo is local on 2718. Weave is connected. Launch is installed but paused. W&B Inference, CoreWeave compute and TypeSafe remain deferred. Read [SPONSORS.md](SPONSORS.md) for each metadata contract and the failed Launch acceptance gate.
