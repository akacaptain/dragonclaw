"""Shared helpers for flow.model.<provider> flows."""

from __future__ import annotations

from typing import Any


def flow_provider_id(flow: Any) -> str:
    prefix = "flow.model."
    flow_id = str(getattr(flow, "flow_id", ""))
    if flow_id.startswith(prefix):
        return flow_id[len(prefix) :].strip().lower()
    return ""


def checklist_id(provider: str, suffix: str) -> str:
    return f"{provider.strip().lower()}_{suffix}"


def primary_satisfies_flow(provider: str, primary: str) -> bool:
    provider = provider.strip().lower()
    primary = primary.strip().lower()
    if not provider or not primary:
        return False
    return primary.startswith(f"{provider}/")


def provider_from_checklist_item_id(item_id: str) -> str | None:
    if item_id.endswith("_auth"):
        return item_id[: -len("_auth")].strip().lower() or None
    if item_id.endswith("_models"):
        return item_id[: -len("_models")].strip().lower() or None
    if item_id.endswith("_primary"):
        return item_id[: -len("_primary")].strip().lower() or None
    return None


def provider_from_session_checklist(checklist) -> str | None:
    for item in checklist:
        provider = provider_from_checklist_item_id(item.id)
        if provider:
            return provider
    return None


def inspect_api_key(provider: str, api_key: str) -> str | None:
    """Return a plain-English warning when key looks wrong; None if OK."""
    key = api_key.strip()
    if not key:
        return "API key is empty."
    provider = provider.strip().lower()
    if provider == "openrouter":
        if key.startswith("Sk-or") or key.startswith("SK-or"):
            return (
                "Key starts with a capital S (Sk-or). OpenRouter keys use lowercase sk-or-v1-… "
                "— a common Docs/Sheets paste typo."
            )
        if not key.lower().startswith("sk-or-"):
            return f"OpenRouter keys usually start with sk-or-v1-; yours starts with {key[:16]!r}."
    return None
