# Local agent and service connections

## Codex

The `neuroloop` MCP server was added to this computer's Codex configuration using:

```powershell
codex mcp add neuroloop -- "D:\NeuroLoop\.venv\Scripts\python.exe" "D:\NeuroLoop\scripts\mcp_stdio.py"
```

This uses the same domain services, database and bounded run queue as the website.
It does not store a copied API token. Start NeuroLoop before queueing model work.
Reload MCP connections or reopen Codex to discover the newly configured tools;
configuration does not retroactively add tools to an already running conversation.

```powershell
codex mcp get neuroloop
```

This reports the configured command without exposing other connections. The
stdio SDK verification uses the exact command above and exercises the actual
NeuroLoop tool implementations. See `real-media-report.json` for its completed
checks. It is distinct from claiming the current Codex conversation has already
reloaded the new tool list.

The official [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
describes stdio servers and command configuration.

## Other local clients

The HTTP endpoint remains `http://127.0.0.1:8010/mcp/`. In **MCP connections**,
use **Test MCP connection** to initialize a real session and discover tool schemas.
**Download client config** supplies an eight-hour bearer token for compatible
HTTP clients. Keep the downloaded token private. The service remains on loopback.

The three added tools are `list_evaluations`, `get_system_status`, and
`get_research_ledger`. The existing evaluation tool now exposes optional TSAM with
the same research acknowledgement required by the browser form.

## Sponsor services

**Check service connections** reports actual connectivity separately from configuration.

| Service | Local role and requirement |
|---|---|
| marimo | Running local notebook on port 2718; reads the actual experiment database |
| Weave | Optional external trace publication; needs a real `WANDB_API_KEY`, `WANDB_PROJECT`, and `NEUROLOOP_WEAVE_ENABLED=true` |
| W&B Inference | Optional constrained experiment planner; requires a real key and `NEUROLOOP_PLANNER_ENABLED=true` |
| ARIA | Planned: requires an implemented versioned job/result bridge, plus Launch credentials, queue and agent; not operational |
| CoreWeave | Cloud compute deferred; this installation runs on the laptop |
| TypeSafe | Disabled by the project requirements |

Put credentials privately in the root `.env`, then restart with Stop/Start-NeuroLoop
to propagate them to all owned services. Do not paste keys into source files,
screenshots or exported evidence. A successful read-only W&B account check does
not establish a successful trace export or ARIA research job. Connection checks
do not make a paid planner request or publish source media.

For the source-audited integration status and acceptance checks, read [SPONSORS.md](SPONSORS.md). ARIA requires missing implementation, not only credentials.
