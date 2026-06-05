"""Parse openclaw models list JSON output and build provider menus."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.oc_picker_catalog import run_picker_catalog
from dragonclaw.openclaw_tools import ToolResult, run_models_list


@dataclass(frozen=True)
class ModelCatalogEntry:
    model_id: str
    display_name: str = ""

    def menu_label(self) -> str:
        name = self.display_name.strip()
        if name and name != self.model_id:
            return f"{name} — {self.model_id}"
        return self.model_id


def models_list_probe_ok(result: ToolResult) -> bool:
    """True when openclaw models list succeeded (connectivity probe, not full catalog)."""
    if not result.ok:
        return False
    if not result.output.strip():
        return False
    if result.output.strip().lower().startswith("no models found"):
        return False
    payload = _extract_json_payload(result.output)
    if payload is None:
        return bool(result.output.strip())
    models = payload.get("models")
    if isinstance(models, list) and len(models) > 0:
        return True
    count = payload.get("count")
    if isinstance(count, int) and count > 0:
        return True
    return bool(parse_models_list_entries(result.output, ""))


def normalize_model_key(key: str, provider: str) -> str:
    """Map OpenClaw CLI model keys to provider-prefixed ids."""
    provider = provider.strip().lower()
    key = key.strip()
    if not key or not provider:
        return key
    lower = key.lower()
    if lower.startswith(f"{provider}/"):
        return key
    if "/" in key:
        return f"{provider}/{key}"
    return f"{provider}/{key}"


def parse_models_list_entries(text: str, provider: str) -> list[ModelCatalogEntry]:
    """Extract model catalog rows from openclaw models list --json output."""
    payload = _extract_json_payload(text)
    if payload is None:
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []

    provider = provider.strip().lower()
    entries: list[ModelCatalogEntry] = []
    seen: set[str] = set()

    for item in models:
        if isinstance(item, str) and item.strip():
            model_id = normalize_model_key(item.strip(), provider) if provider else item.strip()
            if model_id not in seen:
                seen.add(model_id)
                entries.append(ModelCatalogEntry(model_id=model_id))
            continue
        if not isinstance(item, dict):
            continue

        raw_key = ""
        for field in ("key", "id", "model"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                raw_key = value.strip()
                break
        if not raw_key:
            continue

        model_id = normalize_model_key(raw_key, provider) if provider else raw_key
        if model_id in seen:
            continue
        seen.add(model_id)

        display_name = ""
        name_value = item.get("name")
        if isinstance(name_value, str):
            display_name = name_value.strip()

        entries.append(ModelCatalogEntry(model_id=model_id, display_name=display_name))

    return entries


def parse_models_list_json(text: str) -> list[str]:
    """Extract model ids from openclaw models list --json output."""
    return [entry.model_id for entry in parse_models_list_entries(text, "")]


def parse_picker_catalog_json(text: str, provider: str) -> list[ModelCatalogEntry]:
    """Parse oc_picker_catalog.mjs JSON output."""
    payload = _extract_json_payload(text)
    if payload is None:
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    provider = provider.strip().lower()
    entries: list[ModelCatalogEntry] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        raw_key = str(item.get("key") or "").strip()
        if not raw_key:
            model_id = str(item.get("id") or "").strip()
            row_provider = str(item.get("provider") or provider).strip().lower()
            raw_key = normalize_model_key(model_id, row_provider) if model_id else ""
        if not raw_key:
            continue
        model_id = normalize_model_key(raw_key, provider) if provider else raw_key
        if model_id in seen:
            continue
        seen.add(model_id)
        display_name = str(item.get("name") or "").strip()
        entries.append(ModelCatalogEntry(model_id=model_id, display_name=display_name))
    return entries


def catalog_for_provider(workspace_dir: Path, provider: str) -> tuple[list[ModelCatalogEntry], str]:
    """Generic OC catalog: picker live discovery first, models list fallback."""
    provider = provider.strip().lower()
    workspace_dir = workspace_dir.expanduser().resolve()

    picker = run_picker_catalog(workspace_dir, provider)
    if picker.ok:
        entries = parse_picker_catalog_json(picker.output, provider)
        if entries:
            return entries, f"OpenClaw picker catalog ({len(entries)} models)"

    result = run_models_list(workspace_dir, provider)
    if not result.ok:
        detail = picker.error or result.error or result.output or "models list failed"
        return [], detail
    entries = parse_models_list_entries(result.output, provider)
    count = len(entries)
    return entries, f"OpenClaw CLI catalog ({count} models)"


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        loaded = json.loads(match.group(0))
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        return None


def format_model_menu(model_ids: list[str], *, max_show: int = 20) -> str:
    if not model_ids:
        return "(no models returned)"
    lines: list[str] = []
    for index, model_id in enumerate(model_ids[:max_show], start=1):
        lines.append(f"  {index}. {model_id}")
    if len(model_ids) > max_show:
        lines.append(f"  … and {len(model_ids) - max_show} more (type full model id)")
    return "\n".join(lines)
