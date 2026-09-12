# Graphics crash diagnosis — current inspection

**The cause is unresolved. No crash fix or GPU stability claim is established.** This inspection read Windows state and source code without loading models, changing drivers, changing firmware or removing the execution hold.

## Confirmed facts

Windows System events independently report three `VIDEO_DXGKRNL_FATAL_ERROR` bugchecks: September 8 at 18:28:45, September 10 at 15:11:19 and September 10 at 21:47:45 Pacific. Each records `0x113 (0x19, 0x2, 0x10de, 0x27e0)`. The most recent referenced dump is `C:\Windows\Minidump\091026-18312-01.dmp`. Direct access still returns **Access denied**; a subsequent path-not-found message must not be interpreted as proof the dump is absent.

No `windbg`, `cdb`, `kd` or `dumpchk` executable was found on PATH, and no WinDbg Appx package was found. The Windows Kits x64 debugger directory contains support DLLs only. No private readable dump copy exists in `data/diagnostics` at inspection time. Consequently there is no failing-stack analysis, module attribution or failure-bucket determination.

The computer is an Alienware m16 R1 AMD, BIOS 1.24.0, Windows 11 Home build 26200. Graphics devices are an RTX 4080 Laptop GPU (NVIDIA 616.92 / Windows driver 32.0.16.1692) and AMD Radeon 610M (32.0.21045.5002). Last boot was September 11 at 12:38 Pacific. An idle snapshot reported GPU 58°C, 1,812 MiB used of 12,282 MiB, and roughly 10.5 GiB available RAM. Idle headroom is not evidence of stability under inference. No WHEA events were returned by the seven-day read-only query; this does not exclude a hardware fault.

Historical app telemetry reported 90°C GPU and less than 3 GiB available RAM before a crash. That establishes resource pressure, not causation. The [Microsoft stop-code reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x113---video-dxgkrnl-fatal-error) identifies a DirectX graphics-kernel violation; it does not diagnose the responsible driver or component from this code alone.

Raw event/system snapshot: `artifacts/refresh-verification/crash-diagnostic-snapshot.json`.

## Smallest remaining diagnostic step

Use the administrator-copy procedure in [CRASH-RECOVERY.md](CRASH-RECOVERY.md) to make a private readable copy of the latest dump. Analyze that copy with Microsoft's WinDbg and symbols; retain `!analyze -v`, the stack, failure bucket and implicated module/driver versions. Review both graphics adapters because this is a hybrid-graphics laptop; their presence alone does not implicate either driver. Only then select vendor-supported driver, firmware or hardware remediation justified by the diagnosis. Do not alter TDR registry settings or treat a successful run as a driver repair.

## Is CPU-only inference feasible?

It is a plausible separate execution path, not a verified complete fallback yet:

| Component | Source-backed CPU path | Remaining issue |
|---|---|---|
| TRIBE head | Device resolver explicitly supports `cpu` | Fresh end-to-end CPU execution not established by this audit |
| Local INT8 V-JEPA2 | `Int8Linear` dequantizes one layer at a time through ordinary PyTorch operations | CPU BF16/SDPA performance and activation-memory peak require a bounded test |
| W2V-BERT audio | Loader already assigns the audio feature to CPU | RAM/latency still need measurement |
| Llama NF4 | Installed bitsandbytes 0.50.2 includes a CPU DLL | CPU DLL presence alone does not prove the quantized checkpoint loads and executes correctly |
| Whisper / TSAM | Explicit CPU adapters exist | New forward passes still require bounded verification |
| Kragel | NumPy volume sampling/scoring | Registration and scientific validity are separate unresolved gates |

The installed Neuralset text loader calls `from_pretrained` without an explicit CPU device map, then calls `model.to(cpu)`. A quantized loader can select CUDA during construction before that move. A genuine CPU-only test therefore must hide CUDA **before importing torch** and explicitly verify construction/device placement; merely setting the final device is insufficient. [Bitsandbytes installation documentation](https://huggingface.co/docs/bitsandbytes/v0.50.2/en/installation) describes CPU support, but does not certify this application's complete runtime.

The current global execution hold blocks CPU as well as GPU. Also, `hardware_status()` reports CUDA whenever `nvidia-smi` succeeds, even if the requested inference device is CPU. A scoped CPU-only execution authorization and device-aware guard are required; do not remove the GPU quarantine globally just to try CPU. A CPU success would provide a usable alternative, not resolve the Windows graphics crash.

## Revised bounded test proposal

1. Preserve the GPU hold. Add a separately reviewed CPU-only route with CUDA hidden before imports, explicit device placement, one process and no background model queue.
2. Test package/backend construction first without full weights, then one modality at a time in separate processes. Avoid loading text/video/audio together for the first diagnostic pass.
3. Begin with a short audio-only or timed-text input. Record wall time, selected device, model profile, real output hash and peak resident RAM. Enforce a conservative system-RAM reserve and deadline; stop owned work rather than retrying automatically.
4. Only after the first bounded pass succeeds, attempt short video-only and explicit repeated-frame image presentations with the existing frame contract. Do not silently lower frames, change dtype or swap the original model and still label the result as the same profile.
5. Add the audiovisual and optional TSAM/Kragel branches after each independent path passes. Repeat under the same recorded conditions. Report each pass/failure individually and retain the scientific limitations.

This is a test proposal, not an executed acceptance test. No GPU workload was started in this diagnostic inspection.
