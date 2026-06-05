"""Flow definitions loaded from artifacts + built-in flows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from dragonclaw.schema_resolve import resolve_artifacts_dir


@dataclass(frozen=True)
class FlowStep:
    kind: str
    step_id: str
    label: str = ""
    provider: str = ""
    probe: str = ""
    argv: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlowDefinition:
    flow_id: str
    label: str
    steps: tuple[FlowStep, ...] = field(default_factory=tuple)
    checklist: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def load_configure_wizard_catalog() -> dict[str, Any] | None:
    artifacts_dir = resolve_artifacts_dir()
    if artifacts_dir is None:
        return None
    path = artifacts_dir / "configure_wizard_catalog.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _openrouter_flow() -> FlowDefinition:
    return FlowDefinition(
        flow_id="flow.model.openrouter",
        label="Setup OpenRouter",
        steps=(
            FlowStep(kind="probe_install", step_id="install", label="Verify OpenClaw installed"),
            FlowStep(kind="dc_menu", step_id="api_key", label="OpenRouter API key", provider="openrouter"),
            FlowStep(kind="oc_onboard", step_id="onboard", provider="openrouter"),
            FlowStep(kind="oc_json", step_id="model_list", provider="openrouter"),
            FlowStep(
                kind="dc_menu",
                step_id="model_pick",
                label="Choose primary model",
                provider="openrouter",
            ),
            FlowStep(
                kind="oc_json",
                step_id="apply_primary",
                label="Apply primary model",
                provider="openrouter",
            ),
            FlowStep(kind="validate_probe", step_id="models_probe", probe="models_status"),
        ),
        checklist=(
            ("openrouter_auth", "OpenRouter API key configured"),
            ("openrouter_models", "OpenRouter models reachable"),
            ("openrouter_primary", "Primary model set and probed"),
        ),
    )


_BUILTIN_FLOWS: dict[str, FlowDefinition] = {
    "flow.model.openrouter": _openrouter_flow(),
}


def get_flow(flow_id: str) -> FlowDefinition | None:
    return _BUILTIN_FLOWS.get(flow_id.strip())


def list_flows() -> list[FlowDefinition]:
    return list(_BUILTIN_FLOWS.values())


def init_checklist_for_flow(flow: FlowDefinition) -> list:
    from dragonclaw.session_store import ChecklistItem

    return [ChecklistItem(id=item_id, label=label) for item_id, label in flow.checklist]
