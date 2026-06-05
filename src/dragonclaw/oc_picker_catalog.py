"""Live model catalog via OpenClaw picker discovery (runProviderCatalog)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from dragonclaw.installer import USER_NPM_PREFIX, openclaw_binary_path
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.openclaw_validate import resolve_openclaw_home


def resolve_openclaw_dist_dir() -> Path | None:
    """Return openclaw npm package dist/ directory."""
    candidates: list[Path] = []
    binary = openclaw_binary_path()
    if binary is not None:
        resolved = binary.resolve()
        bin_dir = resolved.parent
        for base in (bin_dir.parent, bin_dir.parent.parent, bin_dir):
            candidates.append(base / "lib" / "node_modules" / "openclaw" / "dist")
            candidates.append(base / "node_modules" / "openclaw" / "dist")
    candidates.append(USER_NPM_PREFIX / "lib" / "node_modules" / "openclaw" / "dist")

    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.is_dir() and any(path.glob("provider-discovery-*.js")):
            return path
    return None


def _script_path() -> Path:
    return Path(__file__).resolve().parent / "scripts" / "oc_picker_catalog.mjs"


def run_picker_catalog(workspace_dir: Path, provider: str) -> ToolResult:
    """Invoke Node bridge for live provider catalog (generic, all providers)."""
    provider = provider.strip().lower()
    workspace_dir = workspace_dir.expanduser().resolve()
    dist = resolve_openclaw_dist_dir()
    script = _script_path()
    if dist is None:
        return ToolResult(
            name="picker_catalog",
            ok=False,
            output="",
            error="openclaw dist directory not found",
        )
    if not script.is_file():
        return ToolResult(
            name="picker_catalog",
            ok=False,
            output="",
            error=f"missing bridge script: {script}",
        )

    env = os.environ.copy()
    home = resolve_openclaw_home(workspace_dir)
    if home is not None:
        env["OPENCLAW_HOME"] = str(home)
        env["OPENCLAW_WORKSPACE_DIR"] = str(home)
    env["OPENCLAW_DIST"] = str(dist)

    local_bin = str(USER_NPM_PREFIX / "bin")
    path = env.get("PATH", "")
    if local_bin not in path.split(os.pathsep):
        env["PATH"] = f"{local_bin}{os.pathsep}{path}" if path else local_bin

    cmd = ["node", str(script), "--provider", provider]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(home or workspace_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=90.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult(
            name="picker_catalog",
            ok=False,
            output="",
            error=str(exc),
        )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if not stdout:
        return ToolResult(
            name="picker_catalog",
            ok=False,
            output=stderr,
            error=stderr or f"exit code {proc.returncode}",
            exit_code=proc.returncode,
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return ToolResult(
            name="picker_catalog",
            ok=False,
            output=stdout[:4000],
            error=stderr or "invalid JSON from picker catalog bridge",
            exit_code=proc.returncode,
        )

    if not payload.get("ok"):
        return ToolResult(
            name="picker_catalog",
            ok=False,
            output=stdout,
            error=str(payload.get("error") or stderr or "picker catalog failed"),
            exit_code=proc.returncode,
        )

    return ToolResult(
        name="picker_catalog",
        ok=True,
        output=stdout,
        error=stderr or None,
        exit_code=proc.returncode,
    )
