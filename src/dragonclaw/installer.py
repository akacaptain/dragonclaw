"""OpenClaw installation orchestration for DragonClaw."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_OC_VERSION = "2026.6.1"
MIN_NODE_MAJOR = 18
USER_NPM_PREFIX = Path.home() / ".local"


def openclaw_binary_path(*, npm_prefix: Path | None = None) -> Path | None:
    """Return the openclaw CLI path if installed (PATH or user-local prefix)."""
    found = shutil.which("openclaw")
    if found:
        return Path(found)
    candidates: list[Path] = []
    if npm_prefix is not None:
        candidates.append(npm_prefix / "bin" / "openclaw")
    candidates.append(USER_NPM_PREFIX / "bin" / "openclaw")
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def openclaw_installed() -> bool:
    return openclaw_binary_path() is not None


@dataclass(frozen=True)
class PrereqCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class InstallPlan:
    oc_version: str
    steps: list[str] = field(default_factory=list)
    install_argv: list[str] = field(default_factory=list)
    npm_prefix: Path | None = None
    user_local: bool = False

    def __post_init__(self) -> None:
        if not self.install_argv:
            prefix, user_local = resolve_npm_install_prefix()
            argv = _install_argv(self.oc_version, prefix, force_prefix=user_local)
            object.__setattr__(self, "install_argv", argv)
            object.__setattr__(self, "npm_prefix", prefix)
            object.__setattr__(self, "user_local", user_local)


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    message: str
    command_argv: list[str]
    output: str = ""
    dry_run: bool = False
    npm_prefix: Path | None = None
    user_local: bool = False


def _install_argv(oc_version: str, prefix: Path, *, force_prefix: bool) -> list[str]:
    spec = "openclaw" if oc_version in {"", "latest"} else f"openclaw@{oc_version}"
    argv = ["npm", "install", "-g", spec]
    if force_prefix:
        argv.extend(["--prefix", str(prefix)])
    return argv


def _npm_configured_prefix() -> Path | None:
    npm_bin = shutil.which("npm")
    if not npm_bin:
        return None
    code, out = _run_capture([npm_bin, "config", "get", "prefix"])
    if code != 0:
        return None
    text = out.strip()
    if not text or text == "undefined":
        return None
    return Path(text).expanduser()


def _npm_install_target_writable(prefix: Path) -> bool:
    target = prefix / "lib" / "node_modules"
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".dragonclaw_write_probe"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_npm_install_prefix() -> tuple[Path, bool]:
    """Pick an npm prefix the current user can write to.

    Returns ``(prefix, user_local)`` where ``user_local`` is True when falling
    back to ``~/.local`` instead of npm's configured global prefix.
    """
    configured = _npm_configured_prefix()
    if configured is not None and _npm_install_target_writable(configured):
        return configured, False
    USER_NPM_PREFIX.mkdir(parents=True, exist_ok=True)
    return USER_NPM_PREFIX, True


def ensure_npm_prefix_on_path(prefix: Path) -> None:
    bin_dir = prefix / "bin"
    if not bin_dir.is_dir():
        return
    bin_str = str(bin_dir)
    path = os.environ.get("PATH", "")
    if bin_str not in path.split(os.pathsep):
        os.environ["PATH"] = f"{bin_str}{os.pathsep}{path}"


def _run_capture(argv: list[str], *, timeout_s: float = 30.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return proc.returncode, combined


def check_prerequisites() -> list[PrereqCheck]:
    checks: list[PrereqCheck] = []

    node_bin = shutil.which("node")
    if not node_bin:
        checks.append(PrereqCheck("node", False, "Node.js not found on PATH"))
    else:
        code, out = _run_capture([node_bin, "--version"])
        version = out.strip() if code == 0 else "unknown"
        major_match = re.search(r"v?(\d+)", version)
        major = int(major_match.group(1)) if major_match else 0
        ok = major >= MIN_NODE_MAJOR
        checks.append(
            PrereqCheck(
                "node",
                ok,
                f"{version} (need >={MIN_NODE_MAJOR}.x)" if not ok else version,
            )
        )

    npm_bin = shutil.which("npm")
    if not npm_bin:
        checks.append(PrereqCheck("npm", False, "npm not found on PATH"))
    else:
        code, out = _run_capture([npm_bin, "--version"])
        checks.append(
            PrereqCheck("npm", code == 0, out.strip() if code == 0 else out or "npm --version failed")
        )

    openclaw_bin = shutil.which("openclaw")
    if openclaw_bin:
        code, out = _run_capture([openclaw_bin, "--version"], timeout_s=15.0)
        checks.append(
            PrereqCheck(
                "openclaw",
                code == 0,
                out.splitlines()[0][:120] if code == 0 else out or "openclaw --version failed",
            )
        )
    else:
        checks.append(PrereqCheck("openclaw", False, "not installed"))

    return checks


def build_install_plan(oc_version: str = DEFAULT_OC_VERSION) -> InstallPlan:
    version = oc_version.strip() or DEFAULT_OC_VERSION
    prefix, user_local = resolve_npm_install_prefix()
    target = "~/.local (no admin needed)" if user_local else str(prefix)
    steps = [
        "Verify Node.js and npm are available",
        f"Install OpenClaw ({version}) via npm to {target}",
        "Run openclaw --version to confirm install",
        "Run openclaw setup / workspace initialization if needed",
    ]
    return InstallPlan(
        oc_version=version,
        steps=steps,
        install_argv=_install_argv(version, prefix, force_prefix=user_local),
        npm_prefix=prefix,
        user_local=user_local,
    )


def prerequisites_met() -> tuple[bool, str]:
    checks = check_prerequisites()
    blocking = [c for c in checks if c.name in {"node", "npm"} and not c.ok]
    if blocking:
        return False, "; ".join(f"{c.name}: {c.detail}" for c in blocking)
    return True, "Node and npm are available"


def execute_install(
    plan: InstallPlan,
    *,
    dry_run: bool = True,
    timeout_s: float = 300.0,
    stream_output: bool = True,
) -> InstallResult:
    ok, detail = prerequisites_met()
    if not ok:
        return InstallResult(
            ok=False,
            message=f"Install prerequisites failed: {detail}",
            command_argv=list(plan.install_argv),
            dry_run=dry_run,
        )

    if dry_run:
        return InstallResult(
            ok=True,
            message=f"(Dry run) Would run: {' '.join(plan.install_argv)}",
            command_argv=list(plan.install_argv),
            output=detail,
            dry_run=True,
            npm_prefix=plan.npm_prefix,
            user_local=plan.user_local,
        )

    result = _run_npm_install(plan, timeout_s=timeout_s, stream_output=stream_output)
    if (
        not result.ok
        and not plan.user_local
        and _looks_like_permission_denied(result.output)
    ):
        user_prefix = USER_NPM_PREFIX
        user_prefix.mkdir(parents=True, exist_ok=True)
        retry_argv = _install_argv(plan.oc_version, user_prefix, force_prefix=True)
        retry_plan = InstallPlan(
            oc_version=plan.oc_version,
            install_argv=retry_argv,
            npm_prefix=user_prefix,
            user_local=True,
        )
        result = _run_npm_install(retry_plan, timeout_s=timeout_s, stream_output=stream_output)
    return result


def _looks_like_permission_denied(output: str) -> bool:
    text = output.lower()
    return "eacces" in text or "permission denied" in text


def _run_npm_install(
    plan: InstallPlan,
    *,
    timeout_s: float,
    stream_output: bool,
) -> InstallResult:
    try:
        proc = subprocess.run(
            plan.install_argv,
            capture_output=not stream_output,
            text=not stream_output,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return InstallResult(
            ok=False,
            message=f"Install timed out after {timeout_s}s",
            command_argv=list(plan.install_argv),
            npm_prefix=plan.npm_prefix,
            user_local=plan.user_local,
        )

    combined = ""
    if not stream_output:
        combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    if proc.returncode != 0:
        return InstallResult(
            ok=False,
            message=f"Install failed (exit {proc.returncode})",
            command_argv=list(plan.install_argv),
            output=combined,
            npm_prefix=plan.npm_prefix,
            user_local=plan.user_local,
        )

    if plan.npm_prefix is not None:
        ensure_npm_prefix_on_path(plan.npm_prefix)

    binary = openclaw_binary_path(npm_prefix=plan.npm_prefix)
    if binary is None:
        expected = (
            f"{plan.npm_prefix / 'bin' / 'openclaw'}"
            if plan.npm_prefix is not None
            else str(USER_NPM_PREFIX / "bin" / "openclaw")
        )
        return InstallResult(
            ok=False,
            message="Install failed: npm finished but the openclaw command was not found",
            command_argv=list(plan.install_argv),
            output=(
                f"{combined}\nExpected binary at: {expected}".strip()
                if combined
                else f"Expected binary at: {expected}"
            ),
            npm_prefix=plan.npm_prefix,
            user_local=plan.user_local,
        )

    code, ver_out = _run_capture([str(binary), "--version"], timeout_s=30.0)
    version_line = ver_out.splitlines()[0].strip() if code == 0 and ver_out.strip() else "unknown version"
    if combined:
        combined = f"{combined}\n{ver_out}".strip()
    else:
        combined = ver_out.strip()

    display_path = _display_path(binary)
    message = f"OpenClaw install verified ({version_line}) at {display_path}."
    if plan.user_local:
        message += " Installed to ~/.local (no admin needed)."

    return InstallResult(
        ok=True,
        message=message,
        command_argv=list(plan.install_argv),
        output=combined,
        dry_run=False,
        npm_prefix=plan.npm_prefix,
        user_local=plan.user_local,
    )


def _display_path(path: Path) -> str:
    try:
        home = Path.home()
        if path.is_relative_to(home):
            return f"~/{path.relative_to(home)}"
    except (AttributeError, ValueError):
        pass
    return str(path)


def format_prereq_report() -> str:
    lines = ["Install prerequisites:"]
    for check in check_prerequisites():
        status = "ok" if check.ok else "missing"
        lines.append(f"- {check.name}: {status} ({check.detail})")
    return "\n".join(lines)
