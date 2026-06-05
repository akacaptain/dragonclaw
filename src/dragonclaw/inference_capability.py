"""Probe whether local base-instruct inference is practical on this machine."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import Literal

DeviceKind = Literal["cuda", "mps", "cpu", "unknown"]

MIN_RAM_GB_FOR_LOCAL = 8
DEFAULT_BASE_MODEL = "meta-llama/Llama-3.2-3B-Instruct"


@dataclass(frozen=True)
class CapabilityReport:
    device: DeviceKind
    ram_gb: float | None
    runtime_deps_available: bool
    recommend_remote: bool
    reasons: tuple[str, ...]


def _system_ram_gb() -> float | None:
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        pass
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            return round(int(out) / (1024**3), 1)
        if platform.system() == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024**2), 1)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    return None


def detect_device() -> DeviceKind:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    except ImportError:
        return "unknown"


def runtime_deps_available() -> bool:
    for name in ("torch", "transformers"):
        try:
            __import__(name)
        except ImportError:
            return False
    return True


def probe_local_capability() -> CapabilityReport:
    """Heuristic probe — does not load model weights."""
    device = detect_device()
    ram_gb = _system_ram_gb()
    deps_ok = runtime_deps_available()
    reasons: list[str] = []

    if not deps_ok:
        reasons.append(
            "Local runtime packages (torch, transformers) are not installed. "
            'Install with: pip install -e ".[runtime]"'
        )

    if device == "cpu":
        reasons.append("No GPU detected — local inference runs on CPU and is very slow.")
    elif device == "unknown":
        reasons.append("Could not detect an accelerator for local inference.")

    if ram_gb is not None and ram_gb < MIN_RAM_GB_FOR_LOCAL:
        reasons.append(
            f"System RAM is about {ram_gb:.0f} GB — {MIN_RAM_GB_FOR_LOCAL} GB+ is recommended for local AI."
        )

    recommend_remote = device in {"cpu", "unknown"} or not deps_ok or (
        ram_gb is not None and ram_gb < MIN_RAM_GB_FOR_LOCAL
    )
    return CapabilityReport(
        device=device,
        ram_gb=ram_gb,
        runtime_deps_available=deps_ok,
        recommend_remote=recommend_remote,
        reasons=tuple(reasons),
    )
