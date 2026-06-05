"""Foreground TTY runner for oc_interactive OpenClaw CLI steps."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dragonclaw.installer import USER_NPM_PREFIX, openclaw_binary_path
from dragonclaw.openclaw_validate import resolve_openclaw_home


@dataclass(frozen=True)
class InteractiveResult:
    argv: list[str]
    ok: bool
    exit_code: int
    error: str | None = None


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


def run_openclaw_interactive(
    workspace_dir: Path,
    argv: list[str],
    *,
    use_pty: bool = False,
) -> InteractiveResult:
    """Run openclaw in the foreground with inherited terminal (oc_interactive).

    When ``use_pty`` is True and stdin is not a TTY, allocate a pseudo-terminal
    so scrollable OC wizards still render correctly.
    """
    workspace_dir = workspace_dir.expanduser().resolve()
    binary = openclaw_binary_path()
    if binary is None:
        return InteractiveResult(
            argv=argv,
            ok=False,
            exit_code=127,
            error="openclaw CLI not found on PATH or ~/.local/bin",
        )

    home = resolve_openclaw_home(workspace_dir)
    cwd = str(home) if home is not None else str(workspace_dir)
    cmd = [str(binary), *argv]
    env = _openclaw_env(workspace_dir)

    if use_pty and not sys.stdin.isatty():
        return _run_with_pty(cmd, cwd=cwd, env=env)

    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    except OSError as exc:
        return InteractiveResult(argv=argv, ok=False, exit_code=1, error=str(exc))

    return InteractiveResult(
        argv=argv,
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
    )


def _run_with_pty(cmd: list[str], *, cwd: str, env: dict[str, str]) -> InteractiveResult:
    import pty

    argv = cmd
    pid, master_fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execvpe(argv[0], argv, env)
        raise SystemExit(1)

    try:
        while True:
            try:
                _, status = os.waitpid(pid, 0)
                break
            except OSError:
                break
        exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else status >> 8
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    return InteractiveResult(
        argv=argv[1:] if argv and argv[0].endswith("openclaw") else argv,
        ok=exit_code == 0,
        exit_code=exit_code,
        error=None if exit_code == 0 else f"exit code {exit_code}",
    )
