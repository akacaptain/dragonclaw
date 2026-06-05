"""Load provider catalog artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dragonclaw.schema_resolve import resolve_artifacts_dir


def load_provider_catalog_document() -> dict[str, Any] | None:
    artifacts_dir = resolve_artifacts_dir()
    if artifacts_dir is None:
        return None
    path = artifacts_dir / "provider_catalog.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def menu_primary_providers() -> list[tuple[str, str]]:
    """Return (provider_id, label) for menu_primary providers in catalog order."""
    payload = load_provider_catalog_document()
    if not payload:
        return []
    order = [str(x).lower() for x in (payload.get("menu_primary_order") or [])]
    providers: dict[str, str] = {}
    for raw in payload.get("providers") or []:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id", "")).lower()
        if not pid:
            continue
        if raw.get("menu_primary") or pid in order:
            providers[pid] = str(raw.get("label") or pid)
    if order:
        return [(pid, providers[pid]) for pid in order if pid in providers]
    return sorted(providers.items(), key=lambda item: item[1].lower())


def get_provider_label(provider_id: str) -> str:
    provider_id = provider_id.strip().lower()
    payload = load_provider_catalog_document()
    if not payload:
        return provider_id
    for raw in payload.get("providers") or []:
        if isinstance(raw, dict) and str(raw.get("id", "")).lower() == provider_id:
            return str(raw.get("label") or provider_id)
    return provider_id
