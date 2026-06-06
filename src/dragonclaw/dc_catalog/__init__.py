"""DC-native live model catalog adapters (setup layer)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from dragonclaw.dc_catalog.auth import resolve_provider_api_key
from dragonclaw.dc_catalog.openai_compatible import (
    OpenAICompatibleCatalogConfig,
    fetch_openai_compatible_catalog,
)
from dragonclaw.model_list import ModelCatalogEntry

CatalogFn = Callable[[Path, str, dict[str, str] | None], tuple[list[ModelCatalogEntry], str]]

_OPENAI_COMPATIBLE: dict[str, OpenAICompatibleCatalogConfig] = {
    "openrouter": OpenAICompatibleCatalogConfig(
        models_url="https://openrouter.ai/api/v1/models",
        provider_id="openrouter",
    ),
}


def _fetch_openai_compatible(
    workspace_dir: Path,
    provider_id: str,
    flow_vars: dict[str, str] | None,
) -> tuple[list[ModelCatalogEntry], str]:
    config = _OPENAI_COMPATIBLE.get(provider_id.strip().lower())
    if config is None:
        return [], "no adapter"
    api_key = resolve_provider_api_key(workspace_dir, provider_id, flow_vars=flow_vars)
    entries, error = fetch_openai_compatible_catalog(config, api_key=api_key)
    if error:
        return [], error
    if entries:
        return entries, f"DragonClaw live catalog ({len(entries)} models)"
    if not api_key:
        return [], "API key not found in workspace — configure auth first."
    return [], "Models API returned an empty list."


_ADAPTER_REGISTRY: dict[str, CatalogFn] = {
    provider: _fetch_openai_compatible for provider in _OPENAI_COMPATIBLE
}


def register_catalog_adapter(provider_id: str, fn: CatalogFn) -> None:
    _ADAPTER_REGISTRY[provider_id.strip().lower()] = fn


def has_catalog_adapter(provider_id: str) -> bool:
    return provider_id.strip().lower() in _ADAPTER_REGISTRY


def fetch_dc_catalog(
    workspace_dir: Path,
    provider_id: str,
    *,
    flow_vars: dict[str, str] | None = None,
) -> tuple[list[ModelCatalogEntry], str]:
    """Run DC adapter if registered; returns (entries, source_or_error)."""
    provider_id = provider_id.strip().lower()
    fn = _ADAPTER_REGISTRY.get(provider_id)
    if fn is None:
        return [], "no DC adapter"
    return fn(workspace_dir.expanduser().resolve(), provider_id, flow_vars)
