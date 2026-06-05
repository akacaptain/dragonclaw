"""OpenClaw CLI tools for the DragonClaw agent runtime."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.config_repair import collect_config_health
from dragonclaw.installer import USER_NPM_PREFIX, openclaw_binary_path
from dragonclaw.openclaw_validate import (
    OpenClawValidationReport,
    resolve_openclaw_home,
    run_openclaw_validate,
)
from dragonclaw.workspace_context import build_workspace_snapshot

MAX_TOOL_OUTPUT_CHARS = 8000


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    output: str
    error: str | None = None
    exit_code: int | None = None


def _truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… (truncated)"


def _openclaw_env(workspace_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    home = resolve_openclaw_home(workspace_dir)
    if home is not None:
        env["OPENCLAW_HOME"] = str(home)
    local_bin = str(USER_NPM_PREFIX / "bin")
    path = env.get("PATH", "")
    if local_bin not in path.split(os.pathsep):
        env["PATH"] = f"{local_bin}{os.pathsep}{path}" if path else local_bin
    return env


def _run_openclaw_cli(
    workspace_dir: Path,
    argv: list[str],
    *,
    timeout_s: float = 120.0,
    max_output_chars: int | None = MAX_TOOL_OUTPUT_CHARS,
) -> ToolResult:
    binary_path = openclaw_binary_path()
    if binary_path is None:
        return ToolResult(
            name=argv[0] if argv else "openclaw",
            ok=False,
            output="",
            error="openclaw CLI not found on PATH or ~/.local/bin",
            exit_code=127,
        )

    home = resolve_openclaw_home(workspace_dir)
    cwd = str(home) if home is not None else str(workspace_dir)
    cmd = [str(binary_path), *argv]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=_openclaw_env(workspace_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            name=" ".join(argv),
            ok=False,
            output="",
            error=f"Command timed out after {timeout_s}s: {' '.join(cmd)}",
            exit_code=None,
        )

    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    if max_output_chars is None:
        output = combined
    else:
        output = _truncate(combined, max_output_chars)
    return ToolResult(
        name=" ".join(argv),
        ok=proc.returncode == 0,
        output=output,
        error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
        exit_code=proc.returncode,
    )


def probe_workspace(workspace_dir: Path) -> dict[str, Any]:
    """Workspace file state plus config health (no doctor — use run_doctor)."""
    workspace_dir = workspace_dir.expanduser().resolve()
    snapshot = build_workspace_snapshot(workspace_dir)
    health = collect_config_health(workspace_dir)
    snapshot["config_health"] = {
        "invalid_keys": health.invalid_keys,
        "detail": health.detail,
        "json_parse_error": health.json_parse_error,
    }
    return snapshot


def tool_validate_config(workspace_dir: Path) -> OpenClawValidationReport:
    return run_openclaw_validate(workspace_dir)


def run_doctor(
    workspace_dir: Path,
    *,
    fix: bool = False,
    repair: bool = False,
    non_interactive: bool = True,
) -> ToolResult:
    argv = ["doctor"]
    if fix:
        argv.append("--fix")
    if repair:
        argv.append("--repair")
    if non_interactive:
        argv.append("--non-interactive")
    return _run_openclaw_cli(workspace_dir, argv)


def run_openclaw_version(workspace_dir: Path) -> ToolResult:
    return _run_openclaw_cli(workspace_dir, ["--version"], timeout_s=30.0)


def run_models_status(workspace_dir: Path) -> ToolResult:
    return _run_openclaw_cli(workspace_dir, ["models", "status"], timeout_s=20.0)


def run_models_set(workspace_dir: Path, model_id: str) -> ToolResult:
    model_id = model_id.strip()
    if not model_id:
        return ToolResult(name="models set", ok=False, output="", error="empty model id")
    return _run_openclaw_cli(workspace_dir, ["models", "set", model_id], timeout_s=60.0)


def run_models_list(
    workspace_dir: Path,
    provider: str,
    *,
    timeout_s: float = 45.0,
) -> ToolResult:
    argv = [
        "models",
        "list",
        "--provider",
        provider.strip(),
        "--json",
        "--all",
    ]
    return _run_openclaw_cli(
        workspace_dir,
        argv,
        timeout_s=timeout_s,
        max_output_chars=None,
    )


def execute_command(
    workspace_dir: Path,
    argv: list[str],
    *,
    dry_run: bool = False,
    timeout_s: float = 120.0,
) -> ToolResult:
    if not argv:
        return ToolResult(name="command", ok=False, output="", error="Empty command argv")
    if dry_run:
        return ToolResult(
            name=" ".join(argv),
            ok=True,
            output=f"(Dry run) Would run: {' '.join(argv)}",
            exit_code=0,
        )
    if argv[0] == "openclaw":
        return _run_openclaw_cli(workspace_dir, argv[1:], timeout_s=timeout_s)
    return _run_shell_command(workspace_dir, argv, timeout_s=timeout_s)


def _run_shell_command(workspace_dir: Path, argv: list[str], *, timeout_s: float) -> ToolResult:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            name=" ".join(argv),
            ok=False,
            output="",
            error=f"Command timed out: {' '.join(argv)}",
        )
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return ToolResult(
        name=" ".join(argv),
        ok=proc.returncode == 0,
        output=_truncate(combined),
        error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
        exit_code=proc.returncode,
    )


def build_tool_context(workspace_dir: Path, *, include_doctor: bool = False) -> dict[str, Any]:
    """Probe workspace and OpenClaw CLI for agent prompts."""
    workspace_dir = workspace_dir.expanduser().resolve()
    context: dict[str, Any] = {"workspace": probe_workspace(workspace_dir)}

    validate_report = tool_validate_config(workspace_dir)
    context["openclaw_validate"] = {
        "ok": validate_report.ok,
        "unrecognized_keys": validate_report.unrecognized_keys,
        "error": validate_report.error,
        "raw_output": _truncate(validate_report.raw_output or "", 2000),
    }

    if include_doctor:
        doctor_result = run_doctor(workspace_dir, fix=False, non_interactive=True)
        context["openclaw_doctor"] = {
            "ok": doctor_result.ok,
            "output": doctor_result.output,
            "error": doctor_result.error,
        }

    version_result = run_openclaw_version(workspace_dir)
    if version_result.output:
        context["openclaw_version"] = version_result.output.splitlines()[0][:200]

    return context


def tool_context_for_prompt(workspace_dir: Path, *, include_doctor: bool = False) -> str:
    return json.dumps(
        build_tool_context(workspace_dir, include_doctor=include_doctor),
        indent=2,
        ensure_ascii=True,
    )
