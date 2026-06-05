"""Run OpenClaw CLI config validation and parse results."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dragonclaw.config_apply import read_json_file_state

UNRECOGNIZED_KEY_RE = re.compile(
    r'Unrecognized key:\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
PARSE_FAILED_RE = re.compile(r"JSON5 parse failed|SyntaxError", re.IGNORECASE)


@dataclass
class OpenClawValidationReport:
    ok: bool
    unrecognized_keys: list[str] = field(default_factory=list)
    raw_output: str = ""
    error: str | None = None


def resolve_openclaw_config_dir(path: Path) -> Path | None:
    """Directory that directly contains openclaw.json (DragonClaw workspace root)."""
    path = path.expanduser().resolve()
    nested = path / ".openclaw"
    # Prefer ~/.openclaw over a stray ~/openclaw.json when both exist.
    if nested.is_dir() and (nested / "openclaw.json").is_file():
        return nested
    if (path / "openclaw.json").is_file():
        return path
    return None


def resolve_openclaw_home(workspace_dir: Path) -> Path | None:
    """Map DragonClaw workspace to OPENCLAW_HOME for the openclaw CLI (parent of config dir)."""
    config_dir = resolve_openclaw_config_dir(workspace_dir.expanduser().resolve())
    if config_dir is None:
        return None
    if config_dir.name == ".openclaw":
        return config_dir.parent
    return config_dir


def _keys_from_validate_payload(payload: dict) -> list[str]:
    keys: list[str] = []
    if payload.get("valid") is True:
        return keys
    issues = payload.get("issues") or payload.get("errors") or []
    if not isinstance(issues, list):
        return keys
    for item in issues:
        if not isinstance(item, dict):
            continue
        message = item.get("message")
        if isinstance(message, str):
            keys.extend(UNRECOGNIZED_KEY_RE.findall(message))
        path = item.get("path") or item.get("key")
        if isinstance(path, str) and path not in {"<root>", "root", ""}:
            keys.append(path.strip('"'))

    return sorted(set(keys))


def _parse_validate_output(combined: str) -> tuple[list[str], bool | None]:
    unrecognized = sorted(set(UNRECOGNIZED_KEY_RE.findall(combined)))
    try:
        match = re.search(r"\{.*\}", combined, re.DOTALL)
        if match:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                from_json = _keys_from_validate_payload(payload)
                unrecognized = sorted(set(unrecognized) | set(from_json))
                if payload.get("valid") is True and not unrecognized:
                    return unrecognized, True
                if unrecognized:
                    return unrecognized, False
                if payload.get("valid") is False:
                    return unrecognized, False
    except json.JSONDecodeError:
        pass
    if unrecognized:
        return unrecognized, False
    return unrecognized, None


def _run_validate_with_home(openclaw_home: Path, *, timeout_s: float) -> OpenClawValidationReport:
    binary = shutil.which("openclaw")
    if not binary:
        return OpenClawValidationReport(ok=False, error="openclaw CLI not found on PATH")

    env = os.environ.copy()
    env["OPENCLAW_HOME"] = str(openclaw_home.expanduser().resolve())
    try:
        proc = subprocess.run(
            [binary, "config", "validate", "--json"],
            cwd=str(openclaw_home),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return OpenClawValidationReport(ok=False, error=f"openclaw config validate timed out after {timeout_s}s")

    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    unrecognized, explicit_ok = _parse_validate_output(combined)

    if explicit_ok is True:
        return OpenClawValidationReport(ok=True, raw_output=combined)
    if explicit_ok is False and unrecognized:
        return OpenClawValidationReport(
            ok=False,
            unrecognized_keys=unrecognized,
            raw_output=combined,
            error=f"unrecognized keys: {', '.join(unrecognized)}",
        )
    if proc.returncode == 0 and not unrecognized:
        return OpenClawValidationReport(ok=True, raw_output=combined)

    return OpenClawValidationReport(
        ok=False,
        unrecognized_keys=unrecognized,
        raw_output=combined,
        error=combined[:500] or f"exit code {proc.returncode}",
    )


def run_openclaw_validate_on_config(
    config: dict[str, Any],
    *,
    timeout_s: float = 90.0,
) -> OpenClawValidationReport:
    """Validate a config object without touching the user's on-disk workspace."""
    payload = json.dumps(config, indent=2, ensure_ascii=True) + "\n"
    with tempfile.TemporaryDirectory(prefix="dragonclaw-validate-") as tmp:
        home = Path(tmp)
        oc_dir = home / ".openclaw"
        oc_dir.mkdir()
        (oc_dir / "openclaw.json").write_text(payload, encoding="utf-8")
        return _run_validate_with_home(home, timeout_s=timeout_s)


def run_openclaw_validate(workspace_dir: Path, *, timeout_s: float = 90.0) -> OpenClawValidationReport:
    workspace_dir = workspace_dir.expanduser().resolve()
    config_path = workspace_dir / "openclaw.json"
    state = read_json_file_state(config_path)
    if state.parse_error:
        return OpenClawValidationReport(
            ok=False,
            raw_output=state.raw_text,
            error=f"JSON syntax error: {state.parse_error}",
        )

    openclaw_home = resolve_openclaw_home(workspace_dir)
    if openclaw_home is not None:
        return _run_validate_with_home(openclaw_home, timeout_s=timeout_s)

    if state.parsed is not None:
        return run_openclaw_validate_on_config(state.parsed, timeout_s=timeout_s)

    return OpenClawValidationReport(ok=False, error=f"Config file not found: {config_path}")
