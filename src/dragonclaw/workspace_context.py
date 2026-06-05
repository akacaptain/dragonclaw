"""Load OpenClaw workspace context for LLM prompts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dragonclaw.config_apply import (
    MAX_RAW_CONFIG_CHARS,
    backup_unrecognized_keys,
    list_valid_config_backups,
    read_json_file_state,
)

SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|apikey|api_key|credential|auth)", re.IGNORECASE)


def redact_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY_RE.search(key):
        if isinstance(value, str) and value:
            return value[:4] + "…" if len(value) > 4 else "…"
        return "…"
    if isinstance(value, dict):
        return {k: redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(key, item) for item in value]
    return value


def _truncate_raw(text: str) -> str:
    if len(text) <= MAX_RAW_CONFIG_CHARS:
        return text
    return text[:MAX_RAW_CONFIG_CHARS] + "\n… (truncated)"


def build_workspace_snapshot(workspace_dir: Path) -> dict[str, Any]:
    """Small snapshot for inference — avoid shelling out to openclaw CLI here (it can hang)."""
    workspace_dir = workspace_dir.expanduser().resolve()
    config_path = workspace_dir / "openclaw.json"
    state = read_json_file_state(config_path)
    backups = list_valid_config_backups(workspace_dir)

    snapshot: dict[str, Any] = {
        "workspace_dir": str(workspace_dir),
    }

    if backups:
        snapshot["openclaw.json_available_backups"] = backups
        backup_notes: list[str] = []
        for rel in backups[:6]:
            backup_state = read_json_file_state(workspace_dir / rel)
            if backup_state.parsed is None:
                continue
            invalid = backup_unrecognized_keys(backup_state.parsed)
            if invalid:
                backup_notes.append(f"{rel}: invalid top-level keys {invalid}")
            else:
                backup_notes.append(f"{rel}: passes openclaw config validate")
        if backup_notes:
            snapshot["backup_validate_notes"] = backup_notes

    if state.parse_error:
        snapshot["openclaw.json_parse_error"] = state.parse_error
        snapshot["openclaw.json_raw"] = _truncate_raw(state.raw_text)
        if backups:
            snapshot["openclaw.json_restore_hint"] = (
                f"Use config_patch {{\"__restore_from_backup__\": \"{backups[0]}\"}} to restore from backup."
            )
    else:
        openclaw_config = state.parsed or {}
        meta = openclaw_config.get("meta", {})
        oc_version = meta.get("lastTouchedVersion") if isinstance(meta, dict) else None
        snapshot["config_meta_version"] = oc_version
        snapshot["openclaw.json"] = redact_value("openclaw.json", openclaw_config)

    return snapshot


def snapshot_for_prompt(workspace_dir: Path) -> str:
    snapshot = build_workspace_snapshot(workspace_dir)
    return json.dumps(snapshot, indent=2, ensure_ascii=True)
