"""Select a real local inference device without assuming NVIDIA CUDA."""
from __future__ import annotations

import os


_VALID_DEVICES = {"auto", "cuda", "mps", "cpu"}


def resolve_device(requested: str | None = None) -> str:
    """Return a usable PyTorch device for this machine.

    CUDA remains preferred where it is available. Apple Silicon uses MPS, and
    CPU is retained as a real (slow) fallback rather than fabricating output.
    """
    requested = (requested or os.getenv("NEUROLOOP_INFERENCE_DEVICE", "auto")).strip().lower()
    if requested not in _VALID_DEVICES:
        raise ValueError(f"Unsupported inference device: {requested}")

    from .execution_guard import cpu_verification_enabled
    if cpu_verification_enabled():
        if requested != 'cpu':
            raise RuntimeError('CPU verification cannot select auto, CUDA or MPS')
        return 'cpu'
    if requested == 'cpu':
        return 'cpu'

    import torch

    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable on this machine")
    if requested == "mps" and (
        getattr(torch.backends, "mps", None) is None or not torch.backends.mps.is_available()
    ):
        raise RuntimeError("Apple MPS was requested but is unavailable on this machine")
    return requested
