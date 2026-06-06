"""Resolve provider API keys from workspace (for live catalog adapters)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _read_openclaw_config(workspace_dir: Path) -> dict[str, Any]:
    path = workspace_dir.expanduser().resolve() / "openclaw.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _auth_profile_paths(workspace_dir: Path) -> list[Path]:
    workspace_dir = workspace_dir.expanduser().resolve()
    paths = [
        workspace_dir / "auth-profiles.json",
        workspace_dir / "agents" / "main" / "agent" / "auth-profiles.json",
    ]
    paths.extend(sorted(workspace_dir.glob("**/auth-profiles.json")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _profile_api_key(profile: dict[str, Any]) -> str | None:
    for field in ("apiKey", "api_key", "token", "key"):
        value = profile.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_provider_api_key(
    workspace_dir: Path,
    provider_id: str,
    *,
    flow_vars: dict[str, str] | None = None,
) -> str | None:
    """Read API key from flow session, auth profiles, env vars, or openclaw.json env."""
    provider_id = provider_id.strip().lower()
    if flow_vars:
        session_key = (flow_vars.get("api_key") or "").strip()
        if session_key:
            return session_key

    from dragonclaw.provider_onboard import load_provider_onboard_spec

    spec = load_provider_onboard_spec(provider_id)
    env_var_names: list[str] = []
    if spec:
        for choice in spec.auth_choices:
            if choice.env_var:
                env_var_names.append(choice.env_var.strip())
    if provider_id == "openrouter":
        env_var_names.append("OPENROUTER_API_KEY")

    for name in env_var_names:
        if not name:
            continue
        value = os.environ.get(name, "").strip()
        if value:
            return value

    config = _read_openclaw_config(workspace_dir)
    env_block = config.get("env")
    if isinstance(env_block, dict):
        vars_block = env_block.get("vars")
        if isinstance(vars_block, dict):
            for name in env_var_names:
                value = vars_block.get(name)
                if value is not None and str(value).strip():
                    return str(value).strip()
        for name in env_var_names:
            value = env_block.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()

    for path in _auth_profile_paths(workspace_dir):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        if not isinstance(profiles, dict):
            continue
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            if str(profile.get("provider", "")).lower() != provider_id:
                continue
            key = _profile_api_key(profile)
            if key:
                return key
    return None
