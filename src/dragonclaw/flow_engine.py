"""Run flow steps with validate-gated apply and probes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.flow_model import (
    checklist_id,
    flow_provider_id,
    inspect_api_key,
    primary_satisfies_flow,
    provider_from_session_checklist,
)
from dragonclaw.flow_registry import FlowDefinition, FlowStep, init_checklist_for_flow
from dragonclaw.installer import openclaw_installed
from dragonclaw.model_list import (
    MIN_LIVE_CATALOG_MODELS,
    catalog_for_provider,
    format_models_probe_detail,
    models_catalog_sufficient,
    normalize_model_key,
)
from dragonclaw.openclaw_tools import run_models_set, run_models_status
from dragonclaw.openclaw_validate import run_openclaw_validate
from dragonclaw.presentation import (
    ENTER_MODEL_ID_MANUALLY,
    LOBSTER_MUTED,
    console,
    run_dc_select,
    run_text_prompt,
)
from dragonclaw.provider_catalog import get_provider_label
from dragonclaw.provider_onboard import (
    load_provider_onboard_spec,
    run_provider_onboard_setup,
    workspace_has_provider_auth,
)
from dragonclaw.session_store import ChecklistItem, SessionState, mark_checklist_item


@dataclass
class StepResult:
    completed: bool
    message: str = ""
    failed: bool = False
    global_action: str = ""


def primary_satisfies_openrouter_flow(primary: str) -> bool:
    return primary_satisfies_flow("openrouter", primary)


def _flow_primary_ready(workspace_dir: Path, provider: str) -> bool:
    primary = _read_config_primary(workspace_dir)
    return bool(primary) and primary_satisfies_flow(provider, primary)


def begin_flow(workspace_dir: Path, session: SessionState, flow: FlowDefinition) -> None:
    """Start or resume a flow without wiping probe-based checklist progress."""
    workspace_dir = workspace_dir.expanduser().resolve()
    provider = flow_provider_id(flow)
    _ensure_checklist(flow, session)
    sync_checklist_from_probes(workspace_dir, flow, session)

    if session.active_flow_id == flow.flow_id and session.flow_step_index > 0:
        return

    session.active_flow_id = flow.flow_id
    session.flow_step_index = first_incomplete_step(flow, workspace_dir, session)
    if session.flow_step_index >= len(flow.steps):
        if provider and workspace_has_provider_auth(workspace_dir, provider):
            if _flow_primary_ready(workspace_dir, provider):
                session.flow_step_index = _step_index(flow, "models_probe")
            else:
                session.flow_step_index = _step_index(flow, "model_pick")
        else:
            session.flow_step_index = _step_index(flow, "api_key")


def read_workspace_primary(workspace_dir: Path) -> str:
    return _read_config_primary(workspace_dir)


def refresh_hub_checklist(workspace_dir: Path, session: SessionState) -> None:
    """Re-run model-flow probes before hub display (overwrites stale session checklist)."""
    from dragonclaw.flow_registry import get_flow

    provider = provider_from_session_checklist(session.checklist)
    if not provider:
        return
    flow = get_flow(f"flow.model.{provider}")
    if flow is None:
        return
    if not session.checklist:
        return
    if checklist_id(provider, "auth") not in {item.id for item in session.checklist}:
        return
    _ensure_checklist(flow, session)
    sync_checklist_from_probes(workspace_dir, flow, session)


def sync_checklist_from_probes(
    workspace_dir: Path,
    flow: FlowDefinition,
    session: SessionState,
) -> None:
    """Mark checklist items done when workspace probes succeed."""
    provider = flow_provider_id(flow)
    if not provider:
        return

    if workspace_has_provider_auth(workspace_dir, provider):
        mark_checklist_item(
            session,
            checklist_id(provider, "auth"),
            done=True,
            detail="already configured",
        )

    if workspace_has_provider_auth(workspace_dir, provider):
        entries, source = catalog_for_provider(
            workspace_dir,
            provider,
            flow_vars=session.flow_vars,
        )
        count = len(entries)
        if count > 0:
            detail = format_models_probe_detail(count)
            session.flow_vars[f"{provider}_models_count"] = str(count)
            session.flow_vars[f"{provider}_models_source"] = source
            mark_checklist_item(
                session,
                checklist_id(provider, "models"),
                done=models_catalog_sufficient(count),
                detail=detail,
            )
        else:
            mark_checklist_item(
                session,
                checklist_id(provider, "models"),
                done=False,
                detail=source or "unreachable",
            )

    primary = _read_config_primary(workspace_dir)
    if primary:
        session.flow_vars["primary_model"] = primary
        session.flow_vars["picked_model"] = primary
        if primary_satisfies_flow(provider, primary):
            mark_checklist_item(
                session,
                checklist_id(provider, "primary"),
                done=True,
                detail=primary,
            )
        else:
            mark_checklist_item(
                session,
                checklist_id(provider, "primary"),
                done=False,
                detail=f"{primary} (not {provider})",
            )


def first_incomplete_step(
    flow: FlowDefinition,
    workspace_dir: Path,
    session: SessionState,
) -> int:
    for index, step in enumerate(flow.steps):
        if not _step_satisfied(step, flow, workspace_dir, session):
            return index
    return len(flow.steps)


def _ensure_checklist(flow: FlowDefinition, session: SessionState) -> None:
    expected_labels = {item_id: label for item_id, label in flow.checklist}
    expected_ids = set(expected_labels)
    existing_ids = {item.id for item in session.checklist}

    if not session.checklist or existing_ids != expected_ids:
        session.checklist = init_checklist_for_flow(flow)
        return

    for item in session.checklist:
        fresh_label = expected_labels.get(item.id)
        if fresh_label and item.label != fresh_label:
            item.label = fresh_label


def _step_index(flow: FlowDefinition, step_id: str) -> int:
    for index, step in enumerate(flow.steps):
        if step.step_id == step_id:
            return index
    return 0


def _find_checklist_item(session: SessionState, item_id: str) -> ChecklistItem | None:
    for item in session.checklist:
        if item.id == item_id:
            return item
    return None


def _read_openclaw_config(workspace_dir: Path) -> dict[str, Any]:
    path = workspace_dir.expanduser().resolve() / "openclaw.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_config_primary(workspace_dir: Path) -> str:
    config = _read_openclaw_config(workspace_dir)
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return ""
    defaults = agents.get("defaults")
    if not isinstance(defaults, dict):
        return ""
    model = defaults.get("model")
    if not isinstance(model, dict):
        return ""
    primary = model.get("primary")
    return str(primary).strip() if primary else ""


def _step_provider(step: FlowStep, flow: FlowDefinition) -> str:
    return (step.provider or flow_provider_id(flow) or "openrouter").strip().lower()


def _step_satisfied(
    step: FlowStep,
    flow: FlowDefinition,
    workspace_dir: Path,
    session: SessionState,
) -> bool:
    if step.kind == "probe_install":
        return openclaw_installed()

    provider = _step_provider(step, flow)

    if step.step_id in {"api_key", "onboard"}:
        return workspace_has_provider_auth(workspace_dir, provider)

    if step.kind == "oc_json" and step.step_id == "model_list":
        if _flow_primary_ready(workspace_dir, provider):
            return True
        item = _find_checklist_item(session, checklist_id(provider, "models"))
        return item is not None and item.done

    if step.kind == "dc_menu" and step.step_id == "model_pick":
        return _flow_primary_ready(workspace_dir, provider)

    if step.kind == "oc_json" and step.step_id == "apply_primary":
        return _flow_primary_ready(workspace_dir, provider)

    if step.kind == "validate_probe":
        return _flow_primary_ready(workspace_dir, provider)

    return False


class FlowEngine:
    def __init__(self, workspace_dir: Path, session: SessionState) -> None:
        self.workspace_dir = workspace_dir.expanduser().resolve()
        self.session = session

    def run_flow(self, flow: FlowDefinition) -> StepResult:
        self.session.active_flow_id = flow.flow_id
        _ensure_checklist(flow, self.session)

        while self.session.flow_step_index < len(flow.steps):
            step = flow.steps[self.session.flow_step_index]
            result = self._run_step(flow, step)
            if result.failed:
                return result
            if not result.completed:
                return StepResult(completed=False, message=result.message)
            self.session.flow_step_index += 1

        self.session.active_flow_id = None
        self.session.flow_step_index = 0
        return StepResult(completed=True, message=f"{flow.label} complete.")

    def _run_step(self, flow: FlowDefinition, step: FlowStep) -> StepResult:
        provider = _step_provider(step, flow)

        if step.kind == "probe_install":
            if not openclaw_installed():
                return StepResult(
                    completed=False,
                    failed=True,
                    message="OpenClaw is not installed. Run: dragonclaw install --apply",
                )
            return StepResult(completed=True, message="OpenClaw is installed.")

        if step.kind == "dc_menu" and step.step_id == "api_key":
            if workspace_has_provider_auth(self.workspace_dir, provider):
                mark_checklist_item(
                    self.session,
                    checklist_id(provider, "auth"),
                    done=True,
                    detail="already configured",
                )
                return StepResult(
                    completed=True,
                    message=f"{get_provider_label(provider)} auth already present.",
                )
            provider_label = get_provider_label(provider)
            key = run_text_prompt(
                f"{provider_label} API key\nPaste your key. Stored via validate-gated onboard.",
                secret=True,
            )
            if not key.strip():
                return StepResult(completed=False, message="API key required to continue.")
            warning = inspect_api_key(provider, key)
            if warning:
                console.print(f"\n[{LOBSTER_MUTED}]{warning}[/{LOBSTER_MUTED}]")
                fix = run_text_prompt(
                    "Re-enter API key (or paste corrected key)",
                    secret=True,
                )
                if fix.strip():
                    key = fix
                warning = inspect_api_key(provider, key)
                if warning:
                    return StepResult(completed=False, failed=True, message=warning)
            self.session.flow_vars["api_key"] = key.strip()
            return StepResult(completed=True)

        if step.kind == "dc_menu" and step.step_id == "model_pick":
            return self._run_dc_menu_model_pick(flow, step, provider)

        if step.kind == "oc_onboard":
            if workspace_has_provider_auth(self.workspace_dir, provider):
                mark_checklist_item(
                    self.session,
                    checklist_id(provider, "auth"),
                    done=True,
                    detail="already configured",
                )
                return StepResult(
                    completed=True,
                    message=f"{get_provider_label(provider)} auth already configured.",
                )
            spec = load_provider_onboard_spec(provider)
            if spec is None:
                return StepResult(
                    completed=False,
                    failed=True,
                    message=f"Unknown provider: {provider}",
                )
            api_key = self.session.flow_vars.get("api_key", "")
            try:
                msg = run_provider_onboard_setup(
                    self.workspace_dir,
                    spec,
                    api_key=api_key or None,
                )
            except ValueError as exc:
                return StepResult(completed=False, failed=True, message=str(exc))
            mark_checklist_item(self.session, checklist_id(provider, "auth"), done=True)
            return StepResult(completed=True, message=msg)

        if step.kind == "oc_json" and step.step_id == "model_list":
            entries, source = catalog_for_provider(
                self.workspace_dir,
                provider,
                flow_vars=self.session.flow_vars,
            )
            count = len(entries)
            detail = format_models_probe_detail(count) if count else (source or "unreachable")
            sufficient = models_catalog_sufficient(count)
            self.session.flow_vars[f"{provider}_models_count"] = str(count)
            self.session.flow_vars[f"{provider}_models_source"] = source
            mark_checklist_item(
                self.session,
                checklist_id(provider, "models"),
                done=sufficient,
                detail=detail,
            )
            if sufficient:
                return StepResult(
                    completed=True,
                    message=f"{get_provider_label(provider)} catalog OK ({count} models, {source}).",
                )
            if count > 0:
                return StepResult(
                    completed=True,
                    message=(
                        f"Catalog has {count} models (below {MIN_LIVE_CATALOG_MODELS} bar). "
                        f"Source: {source}. Continuing to model picker."
                    ),
                )
            return StepResult(
                completed=True,
                message=(
                    f"Model catalog unreachable or empty ({source}). "
                    "You can still enter a model id manually."
                ),
            )

        if step.kind == "oc_json" and step.step_id == "apply_primary":
            existing_primary = _read_config_primary(self.workspace_dir)
            if existing_primary and primary_satisfies_flow(provider, existing_primary):
                self.session.flow_vars["primary_model"] = existing_primary
                mark_checklist_item(
                    self.session,
                    checklist_id(provider, "primary"),
                    done=True,
                    detail=existing_primary,
                )
                return StepResult(
                    completed=True,
                    message=f"Primary model already set to {existing_primary}.",
                )
            if existing_primary and not primary_satisfies_flow(provider, existing_primary):
                return StepResult(
                    completed=False,
                    failed=True,
                    message=(
                        f"Primary is {existing_primary} — pick a {provider}/ model "
                        "to finish this flow."
                    ),
                )
            model_id = self.session.flow_vars.get("picked_model", "").strip()
            if not model_id:
                return StepResult(
                    completed=False,
                    failed=True,
                    message="No model selected — pick a model first.",
                )
            result = run_models_set(self.workspace_dir, model_id)
            if not result.ok:
                detail = result.error or result.output or "models set failed"
                return StepResult(completed=False, failed=True, message=detail)
            primary = _read_config_primary(self.workspace_dir)
            if not primary:
                return StepResult(
                    completed=False,
                    failed=True,
                    message=f"openclaw models set ran but primary not in config ({model_id}).",
                )
            if not primary_satisfies_flow(provider, primary):
                return StepResult(
                    completed=False,
                    failed=True,
                    message=f"Primary {primary} is not a {provider} model.",
                )
            self.session.flow_vars["primary_model"] = primary
            mark_checklist_item(
                self.session,
                checklist_id(provider, "primary"),
                done=True,
                detail=primary,
            )
            return StepResult(completed=True, message=f"Primary model set to {primary}.")

        if step.kind == "validate_probe":
            validate = run_openclaw_validate(self.workspace_dir)
            if not validate.ok:
                detail = validate.error or validate.raw_output[:200]
                return StepResult(completed=False, failed=True, message=f"Validate failed: {detail}")
            if step.probe == "models_status":
                status = run_models_status(self.workspace_dir)
                if not status.ok:
                    return StepResult(
                        completed=False,
                        failed=True,
                        message=status.error or status.output or "models status failed",
                    )
                primary = (
                    self.session.flow_vars.get("primary_model")
                    or _read_config_primary(self.workspace_dir)
                )
                if not primary or not primary_satisfies_flow(provider, primary):
                    return StepResult(
                        completed=False,
                        failed=True,
                        message=(
                            f"{get_provider_label(provider)} primary not set — pick a "
                            f"{provider}/ model before finishing this flow."
                        ),
                    )
                if primary not in status.output:
                    return StepResult(
                        completed=False,
                        failed=True,
                        message=f"Primary model {primary} not seen in models status.",
                    )
                mark_checklist_item(
                    self.session,
                    checklist_id(provider, "primary"),
                    done=True,
                    detail=primary,
                )
            return StepResult(completed=True, message="Probes passed.")

        return StepResult(completed=False, failed=True, message=f"Unknown step kind: {step.kind}")

    def _run_dc_menu_model_pick(
        self,
        flow: FlowDefinition,
        step: FlowStep,
        provider: str,
    ) -> StepResult:
        if _flow_primary_ready(self.workspace_dir, provider):
            primary = _read_config_primary(self.workspace_dir)
            self.session.flow_vars["picked_model"] = primary
            self.session.flow_vars["primary_model"] = primary
            return StepResult(
                completed=True,
                message=f"Primary model already set to {primary}.",
            )

        entries, source = catalog_for_provider(
            self.workspace_dir,
            provider,
            flow_vars=self.session.flow_vars,
        )
        label_to_id: dict[str, str] = {}
        for entry in entries:
            label_to_id[entry.menu_label()] = entry.model_id

        options = list(label_to_id.keys())
        if not options:
            console.print(
                f"\n[{LOBSTER_MUTED}]No models in catalog ({source}). "
                f"Enter model id manually.[/{LOBSTER_MUTED}]"
            )
            model_id = run_text_prompt(
                f"Model id (e.g. {provider}/auto)",
            ).strip()
            if not model_id:
                return StepResult(completed=False, message="Model selection cancelled.")
            model_id = normalize_model_key(model_id, provider)
            self.session.flow_vars["picked_model"] = model_id
            return StepResult(completed=True, message=f"Selected {model_id}.")

        options.append(ENTER_MODEL_ID_MANUALLY)
        choice = run_dc_select(
            f"Choose primary model — {source}",
            options,
        )
        if choice == ENTER_MODEL_ID_MANUALLY:
            model_id = run_text_prompt(f"Model id (e.g. {provider}/auto)").strip()
            if not model_id:
                return StepResult(completed=False, message="Model selection cancelled.")
            model_id = normalize_model_key(model_id, provider)
        else:
            model_id = label_to_id.get(choice, "")
            if not model_id:
                return StepResult(completed=False, failed=True, message="Invalid menu selection.")

        self.session.flow_vars["picked_model"] = model_id
        return StepResult(completed=True, message=f"Selected {model_id}.")
