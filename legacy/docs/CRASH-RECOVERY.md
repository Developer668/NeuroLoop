# Graphics crash recovery

**Do not resume GPU inference yet.** Windows recorded another `VIDEO_DXGKRNL_FATAL_ERROR (0x113)` at September 10, 2026 21:47:45 Pacific. The local API, saved-data review, marimo and read-only MCP work; model execution and Launch are paused.

## Evidence

| Item | Recorded value |
|---|---|
| Latest stop code | `0x113 (0x19, 0x2, 0x10de, 0x27e0)` |
| Latest dump | `C:\Windows\Minidump\091026-18312-01.dmp` |
| Windows report ID | `a21eca60-08f2-4408-92fc-9e80b156d9c1` |
| Earlier same-day event | 15:11:19; `091026-17953-01.dmp` |
| Earlier incident | September 8; `090826-17765-01.dmp` |
| Hardware | RTX 4080 Laptop GPU, 12 GB VRAM, approximately 32 GB RAM |
| Reported NVIDIA driver | 616.92 |
| Interrupted run | `5df6542e-b183-4a08-b05e-adcf81175aed` |
| Work completed | Baseline prediction, 89.437 seconds; actual array saved |
| Work interrupted | Reference evaluation, stage “Predicting cortical responses” |
| Saved telemetry | GPU reached 90°C; available RAM fell below 3 GiB; the last sample is earlier than the Windows event |

Raw receipts are under `data/verification/release`: `windows-bugchecks.json`, `stability-0e2bcff4-94fe-4759-bf64-972e464bfb41.json` and the matching Launch receipt. The monitor cannot report what happened after the host stopped recording.

Microsoft describes 0x113 as a graphics-kernel violation. That stop code alone does not distinguish a driver defect, hardware issue, thermal problem or another cause. [Microsoft bug-check reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x113---video-dxgkrnl-fatal-error).

The dump directory denies this process access. No readable dump analysis has been completed, and no driver, firmware, registry, power or clock settings were changed. A successful earlier inference does not resolve this failure.

The matching Windows Error Reporting archive was located too, but its contents also deny access. The readable System event log confirms the event and dump path; it does not provide the failing stack.

## What recovery changed

- Preserved the database, media, model weights, caches and completed predictions. All 29 arrays and 32 media hashes passed the recovery audit.
- Marked the interrupted local run/proposal failed; confirmed the W&B run is crashed and its local-status summary is failed. The old receipt's running status is retained as pre-recovery history.
- Added `data/inference-quarantine.json`. Startup omits the model worker and Launch agent; website/API/MCP model queue submissions and standalone executors reject new work.
- Added a conservative runtime guardian: check telemetry every three seconds, terminate the owned process tree at 82°C GPU or below 3 GiB available RAM, persist a hold, preserve completed evidence. Missing telemetry stops execution too. Controlled-process tests verify the mechanism; this is not a proven driver-crash fix.
- Reopened Edge for evidence review and sponsor verification. No further model execution was attempted.

## Required diagnostic handoff

An administrator can copy the latest dump into the project without changing its source permissions. In an **Administrator PowerShell**, run:

```powershell
New-Item -ItemType Directory -Force D:\NeuroLoop\data\diagnostics | Out-Null
Copy-Item -LiteralPath C:\Windows\Minidump\091026-18312-01.dmp -Destination D:\NeuroLoop\data\diagnostics\091026-18312-01.dmp
```

Keep the dump private; it may contain system/process memory. Open the local copy in Microsoft's WinDbg and record `!analyze -v`, the failure bucket, implicated module, stack and driver versions. Use official Microsoft symbols. [WinDbg installation and setup](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/).

If diagnosis indicates a driver/firmware/hardware issue, resolve it through the laptop/NVIDIA vendor's supported process. Do not treat temperature correlation as enough to select a driver change. Once diagnosed, agree a revised workload and resource budget before explicitly lifting the hold. Repeat stability verification and complete the second-installation/Launch gates only then.

The RTX 4080 Laptop has run this quantized pipeline, but this installation has **not demonstrated dependable full-workflow stability**. No promise that it will run without crashing is justified by current evidence.
