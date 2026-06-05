"""OpenClaw config validation helpers for the LLM planner runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.config_apply import (
    REMOVE_KEYS_FIELD,
    REPLACE_FILE_FIELD,
    read_json_file_state,
    resolve_patch_result,
)
from dragonclaw.openclaw_validate import (
    PARSE_FAILED_RE,
    UNRECOGNIZED_KEY_RE,
    run_openclaw_validate,
    run_openclaw_validate_on_config,
)


@dataclass(frozen=True)
class ConfigHealth:
    invalid_keys: list[str]
    detail: str
    json_parse_error: str | None


def collect_config_health(workspace_dir: Path) -> ConfigHealth:
    """Summarize config problems for LLM context."""
    workspace_dir = workspace_dir.expanduser().resolve()
    config_path = workspace_dir / "openclaw.json"
    state = read_json_file_state(config_path)

    notes: list[str] = []
    invalid: set[str] = set()

    if state.parse_error:
        notes.append(f"openclaw.json JSON syntax error: {state.parse_error}")
    else:
        oc_report = run_openclaw_validate(workspace_dir)
        if oc_report.unrecognized_keys:
            invalid.update(oc_report.unrecognized_keys)
            notes.append(f"openclaw validate: unrecognized keys {oc_report.unrecognized_keys}")
        elif oc_report.error and "timed out" in oc_report.error:
            notes.append(f"openclaw validate: {oc_report.error}")
        elif not oc_report.ok and oc_report.raw_output:
            invalid.update(UNRECOGNIZED_KEY_RE.findall(oc_report.raw_output))
            if PARSE_FAILED_RE.search(oc_report.raw_output):
                notes.append(f"openclaw validate: {oc_report.raw_output[:400]}")
            else:
                notes.append("openclaw validate: failed")

    return ConfigHealth(
        invalid_keys=sorted(invalid),
        detail="\n".join(notes),
        json_parse_error=state.parse_error,
    )


def collect_invalid_top_level_keys(workspace_dir: Path) -> tuple[list[str], str]:
    health = collect_config_health(workspace_dir)
    return health.invalid_keys, health.detail


def is_remove_only_plan(plan: dict[str, dict]) -> bool:
    for patch in plan.values():
        if set(patch.keys()) - {REMOVE_KEYS_FIELD}:
            return False
    return bool(plan)


def is_replace_only_plan(plan: dict[str, dict]) -> bool:
    for patch in plan.values():
        if set(patch.keys()) - {REPLACE_FILE_FIELD}:
            return False
    return bool(plan)


def validate_merged_openclaw(
    workspace_dir: Path,
    plan: dict[str, dict],
    schema_path: Path | None = None,
) -> tuple[bool, str]:
    """Validate the post-merge config with openclaw CLI (not extracted schema.json)."""
    del schema_path
    if "openclaw.json" not in plan:
        return True, ""

    workspace_dir = workspace_dir.expanduser().resolve()
    patch = plan["openclaw.json"]
    state = read_json_file_state(workspace_dir / "openclaw.json")

    try:
        merged = resolve_patch_result(state.parsed, patch, workspace_dir=workspace_dir, target_filename="openclaw.json")
    except ValueError as exc:
        return False, str(exc)

    if is_remove_only_plan(plan):
        for key in patch.get(REMOVE_KEYS_FIELD, []):
            if isinstance(key, str) and key in merged:
                return False, f"Patch did not remove invalid key: {key}"

    report = run_openclaw_validate_on_config(merged)
    if report.ok:
        return True, ""
    if report.unrecognized_keys:
        return False, (
            "openclaw config validate reports unrecognized keys: " + ", ".join(report.unrecognized_keys)
        )
    snippet = (report.raw_output or report.error or "validation failed")[:400]
    return False, f"openclaw config validate failed: {snippet}"
