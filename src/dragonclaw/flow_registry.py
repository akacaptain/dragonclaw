"""Flow definitions loaded from artifacts + built-in flows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dragonclaw.flow_model import checklist_id, flow_provider_id, primary_satisfies_flow
from dragonclaw.provider_catalog import get_provider_label, load_provider_catalog_document
from dragonclaw.provider_onboard import load_provider_onboard_spec
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


def build_model_provider_flow(provider_id: str, label: str) -> FlowDefinition:
    """Generic flow.model.<provider> for API-key providers."""
    provider_id = provider_id.strip().lower()
    provider_label = get_provider_label(provider_id)
    return FlowDefinition(
        flow_id=f"flow.model.{provider_id}",
        label=label,
        steps=(
            FlowStep(
                kind="probe_install",
                step_id="install",
                label="Verify OpenClaw installed",
            ),
            FlowStep(
                kind="dc_menu",
                step_id="api_key",
                label=f"{provider_label} API key",
                provider=provider_id,
            ),
            FlowStep(kind="oc_onboard", step_id="onboard", provider=provider_id),
            FlowStep(kind="oc_json", step_id="model_list", provider=provider_id),
            FlowStep(
                kind="dc_menu",
                step_id="model_pick",
                label="Choose primary model",
                provider=provider_id,
            ),
            FlowStep(
                kind="oc_json",
                step_id="apply_primary",
                label="Apply primary model",
                provider=provider_id,
            ),
            FlowStep(kind="validate_probe", step_id="models_probe", probe="models_status"),
        ),
        checklist=(
            (checklist_id(provider_id, "auth"), f"{provider_label} API key configured"),
            (checklist_id(provider_id, "models"), f"{provider_label} models reachable"),
            (checklist_id(provider_id, "primary"), "Primary model set and probed"),
        ),
    )


def _load_model_provider_flows() -> dict[str, FlowDefinition]:
    payload = load_provider_catalog_document() or {}
    order = [str(item).lower() for item in (payload.get("menu_primary_order") or [])]
    providers: dict[str, dict[str, Any]] = {}
    for raw in payload.get("providers") or []:
        if isinstance(raw, dict):
            pid = str(raw.get("id", "")).lower()
            if pid:
                providers[pid] = raw

    flows: dict[str, FlowDefinition] = {}
    candidate_ids = order or sorted(providers)
    for pid in candidate_ids:
        raw = providers.get(pid)
        if raw is None:
            continue
        if not raw.get("menu_primary") and pid not in order:
            continue
        spec = load_provider_onboard_spec(pid)
        if spec is None or not spec.requires_api_key():
            continue
        choice = spec.preferred_setup_choice()
        if choice is None or choice.method != "api-key":
            continue
        # Phase 2 hub: OpenRouter only; factory supports more when routed explicitly.
        if pid != "openrouter":
            continue
        label = f"Setup {raw.get('label') or pid.replace('-', ' ').title()}"
        flows[f"flow.model.{pid}"] = build_model_provider_flow(pid, label)

    if "flow.model.openrouter" not in flows:
        flows["flow.model.openrouter"] = build_model_provider_flow("openrouter", "Setup OpenRouter")
    return flows


_BUILTIN_FLOWS: dict[str, FlowDefinition] = _load_model_provider_flows()


def get_flow(flow_id: str) -> FlowDefinition | None:
    return _BUILTIN_FLOWS.get(flow_id.strip())


def list_flows() -> list[FlowDefinition]:
    return list(_BUILTIN_FLOWS.values())


def _checklist_by_id(session) -> dict[str, object]:
    return {item.id: item for item in session.checklist}


def hub_label_for_flow(
    flow: FlowDefinition,
    session,
    *,
    workspace_dir: Path | None = None,
) -> str:
    """Context-aware hub row label (aliases map back to flow.flow_id)."""
    from dragonclaw.flow_engine import read_workspace_primary

    provider = flow_provider_id(flow)
    if not provider:
        return flow.label

    items = _checklist_by_id(session)
    auth = items.get(checklist_id(provider, "auth"))
    models = items.get(checklist_id(provider, "models"))
    primary_item = items.get(checklist_id(provider, "primary"))

    config_primary = read_workspace_primary(workspace_dir) if workspace_dir else ""
    primary_ok = (
        primary_satisfies_flow(provider, config_primary)
        if config_primary
        else (primary_item is not None and primary_item.done)
    )

    if primary_ok:
        return f"Review {get_provider_label(provider)} setup"
    if auth is not None and auth.done:
        if models is not None and not models.done:
            return f"{flow.label} (thin model catalog)"
        return f"Set primary model ({get_provider_label(provider)})"
    return flow.label


def hub_labels_for_session(
    session,
    *,
    workspace_dir: Path | None = None,
) -> list[tuple[str, str]]:
    return [
        (hub_label_for_flow(flow, session, workspace_dir=workspace_dir), flow.flow_id)
        for flow in list_flows()
    ]


def resolve_flow_id_from_hub_label(
    choice: str,
    session,
    *,
    workspace_dir: Path | None = None,
) -> str | None:
    for label, flow_id in hub_labels_for_session(session, workspace_dir=workspace_dir):
        if choice == label:
            return flow_id
    for flow in list_flows():
        if choice == flow.label:
            return flow.flow_id
    return None


def hub_next_hint(session, *, workspace_dir: Path | None = None) -> str | None:
    """Optional line above hub menu when checklist has an obvious next step."""
    from dragonclaw.flow_engine import read_workspace_primary
    from dragonclaw.flow_model import provider_from_session_checklist

    provider = provider_from_session_checklist(session.checklist)
    if not provider:
        return None

    items = _checklist_by_id(session)
    models = items.get(checklist_id(provider, "models"))
    primary_item = items.get(checklist_id(provider, "primary"))
    auth = items.get(checklist_id(provider, "auth"))

    config_primary = read_workspace_primary(workspace_dir) if workspace_dir else ""
    if config_primary and not primary_satisfies_flow(provider, config_primary):
        return (
            f"Next: primary is {config_primary} — pick a {provider}/ model "
            "to finish this flow."
        )

    if primary_item is not None and primary_item.done and config_primary:
        if primary_satisfies_flow(provider, config_primary):
            return None

    if models is not None and not models.done:
        return (
            "Next: model catalog is thin or unreachable — pick a model manually "
            "or use Ask DragonClaw."
        )

    if primary_item is not None and not primary_item.done:
        if auth is not None and auth.done:
            return "Next: choose your primary model."
    return None


def init_checklist_for_flow(flow: FlowDefinition) -> list:
    from dragonclaw.session_store import ChecklistItem

    return [ChecklistItem(id=item_id, label=label) for item_id, label in flow.checklist]
