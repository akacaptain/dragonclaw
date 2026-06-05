"""Deterministic intent routing to flow_id."""

from __future__ import annotations

import re

from dragonclaw.flow_registry import list_flows

_OPENROUTER_RE = re.compile(r"\b(openrouter|setup\s+openrouter|open\s*router)\b", re.I)
_DOCTOR_RE = re.compile(r"\b(doctor|fix my setup|troubleshoot)\b", re.I)
_VALIDATE_RE = re.compile(r"\b(validate|validation)\b", re.I)


def route_intent(text: str) -> str | None:
    """Map user text to flow_id or action; None = hub / no match."""
    stripped = text.strip()
    if not stripped:
        return None
    if _OPENROUTER_RE.search(stripped):
        return "flow.model.openrouter"
    if _DOCTOR_RE.search(stripped):
        return "action.doctor"
    if _VALIDATE_RE.search(stripped):
        return "action.validate"
    if stripped.isdigit():
        menu = hub_menu_options()
        index = int(stripped)
        if 1 <= index <= len(menu):
            return menu[index - 1][1]
    lowered = stripped.lower()
    for label, flow_id in hub_menu_options():
        if lowered == label.lower():
            return flow_id
    return None


def hub_menu_options() -> list[tuple[str, str | None]]:
    """Registered setup flows only — no validate/doctor stubs."""
    return [(flow.label, flow.flow_id) for flow in list_flows()]


def hub_menu_labels() -> list[str]:
    return [label for label, _ in hub_menu_options()]
