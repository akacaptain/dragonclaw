"""Apply a multi-file OpenClaw config plan to disk."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.configurator import merge_patch

# Patch key listing top-level JSON keys to delete before merge.
REMOVE_KEYS_FIELD = "__remove_keys__"
# Replace entire file when the on-disk JSON cannot be parsed or merge is unsafe.
REPLACE_FILE_FIELD = "__replace_file__"
# Restore from a workspace-local backup file (runtime reads unredacted JSON).
RESTORE_FROM_BACKUP_FIELD = "__restore_from_backup__"

BACKUP_SUFFIXES = (".bak", ".bak.1", ".bak.2", ".bak.3", ".bak.4")
MAX_RAW_CONFIG_CHARS = 12_000


@dataclass(frozen=True)
class JsonFileState:
    parsed: dict[str, Any] | None
    raw_text: str
    parse_error: str | None


def read_json_file_state(path: Path) -> JsonFileState:
    if not path.exists():
        return JsonFileState(parsed={}, raw_text="", parse_error=None)
    raw_text = path.read_text(encoding="utf-8")
    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return JsonFileState(parsed=None, raw_text=raw_text, parse_error=str(exc))
    if not isinstance(loaded, dict):
        return JsonFileState(
            parsed=None,
            raw_text=raw_text,
            parse_error=f"Expected JSON object in {path}",
        )
    return JsonFileState(parsed=loaded, raw_text=raw_text, parse_error=None)


def list_valid_config_backups(workspace_dir: Path, *, filename: str = "openclaw.json") -> list[str]:
    """Backups that are parseable JSON (may still fail openclaw config validate)."""
    workspace_dir = workspace_dir.expanduser().resolve()
    found: list[str] = []
    for suffix in BACKUP_SUFFIXES:
        rel = f"{filename}{suffix}"
        candidate = workspace_dir / rel
        if not candidate.exists():
            continue
        state = read_json_file_state(candidate)
        if state.parsed is not None and state.parse_error is None:
            found.append(rel)
    return found


def backup_unrecognized_keys(parsed: dict[str, Any]) -> list[str]:
    """Keys openclaw config validate rejects in this object (not on disk)."""
    from dragonclaw.openclaw_validate import run_openclaw_validate_on_config

    report = run_openclaw_validate_on_config(parsed)
    return list(report.unrecognized_keys)


def select_restore_target(
    workspace_dir: Path,
    *,
    filename: str = "openclaw.json",
    preferred: str | None = None,
) -> tuple[str, list[str]]:
    """Pick a backup to restore and any top-level keys to remove after restore.

    Prefers a backup that passes validate as-is; otherwise the first parseable backup
    plus __remove_keys__ for invalid top-level keys in that backup.
    """
    workspace_dir = workspace_dir.expanduser().resolve()
    parseable = list_valid_config_backups(workspace_dir, filename=filename)
    if not parseable:
        raise ValueError(f"No parseable {filename} backup found in workspace.")

    ordered = list(parseable)
    if preferred:
        pref = preferred.strip()
        if pref in ordered:
            ordered = [pref] + [b for b in ordered if b != pref]
        else:
            for name in ordered:
                if pref in name or name.endswith(pref):
                    ordered = [name] + [b for b in ordered if b != name]
                    break

    for rel in ordered:
        state = read_json_file_state(workspace_dir / rel)
        assert state.parsed is not None
        invalid = backup_unrecognized_keys(state.parsed)
        if not invalid:
            return rel, []
    rel = ordered[0]
    state = read_json_file_state(workspace_dir / rel)
    assert state.parsed is not None
    return rel, backup_unrecognized_keys(state.parsed)


def _resolve_backup_file(workspace_dir: Path, value: Any, *, filename: str = "openclaw.json") -> Path:
    workspace_dir = workspace_dir.expanduser().resolve()
    if value in {True, "latest", "auto", None}:
        backups = list_valid_config_backups(workspace_dir, filename=filename)
        if not backups:
            raise ValueError(f"No valid {filename} backup found in workspace.")
        return workspace_dir / backups[0]

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{RESTORE_FROM_BACKUP_FIELD} must be a backup filename or true.")

    rel = value.strip()
    candidate = (workspace_dir / rel).resolve()
    if workspace_dir not in {candidate, *candidate.parents}:
        raise ValueError(f"Backup path must stay inside workspace: {rel}")
    state = read_json_file_state(candidate)
    if state.parsed is None:
        raise ValueError(f"Backup file is not valid JSON: {rel} ({state.parse_error})")
    return candidate


def _read_json_file(path: Path) -> dict:
    state = read_json_file_state(path)
    if state.parse_error:
        raise ValueError(
            f"{path.name} is not valid JSON ({state.parse_error}). "
            f"Use {REPLACE_FILE_FIELD} or {RESTORE_FROM_BACKUP_FIELD}."
        )
    return state.parsed or {}


def resolve_patch_result(
    current: dict[str, Any] | None,
    patch: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
    target_filename: str = "openclaw.json",
) -> dict[str, Any]:
    """Apply patch to current config, or replace/restore the file when requested."""
    if RESTORE_FROM_BACKUP_FIELD in patch:
        if workspace_dir is None:
            raise ValueError(f"{RESTORE_FROM_BACKUP_FIELD} requires workspace context.")
        backup_path = _resolve_backup_file(workspace_dir, patch[RESTORE_FROM_BACKUP_FIELD], filename=target_filename)
        backup_state = read_json_file_state(backup_path)
        assert backup_state.parsed is not None
        restored = dict(backup_state.parsed)
        remove_keys = patch.get(REMOVE_KEYS_FIELD)
        if isinstance(remove_keys, list):
            for key in remove_keys:
                if isinstance(key, str):
                    restored.pop(key, None)
        return restored

    if REPLACE_FILE_FIELD in patch:
        replacement = patch[REPLACE_FILE_FIELD]
        if not isinstance(replacement, dict):
            raise ValueError(f"{REPLACE_FILE_FIELD} must be a JSON object.")
        return dict(replacement)

    if current is None:
        raise ValueError(
            f"Cannot merge patch into unparseable config. "
            f"Use {REPLACE_FILE_FIELD} with the complete fixed object, "
            f"or {RESTORE_FROM_BACKUP_FIELD} with a backup filename."
        )
    return apply_patch_to_document(current, patch)


def apply_patch_to_document(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge patch into current and apply key removals."""
    working = dict(patch)
    working.pop(REPLACE_FILE_FIELD, None)
    working.pop(RESTORE_FROM_BACKUP_FIELD, None)
    remove_keys = working.pop(REMOVE_KEYS_FIELD, None)
    merged = merge_patch(current, working)
    if isinstance(remove_keys, list):
        for key in remove_keys:
            if isinstance(key, str):
                merged.pop(key, None)
    return merged


def apply_config_plan(
    workspace_dir: Path,
    plan: dict[str, dict],
    dry_run: bool = False,
    create_backups: bool = True,
) -> list[Path]:
    workspace_dir = workspace_dir.expanduser().resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for rel_path, patch in sorted(plan.items()):
        target = (workspace_dir / rel_path).resolve()
        if workspace_dir not in {target, *target.parents}:
            raise ValueError(f"Refusing to write outside workspace: {target}")
        if not target.suffix == ".json":
            raise ValueError(f"Only .json targets are supported: {rel_path}")

        state = read_json_file_state(target)
        merged = resolve_patch_result(
            state.parsed,
            patch,
            workspace_dir=workspace_dir,
            target_filename=target.name,
        )
        written.append(target)

        if dry_run:
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if create_backups and target.exists():
            backup = target.with_suffix(target.suffix + ".bak")
            backup.write_text(state.raw_text or target.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(json.dumps(merged, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return written
