"""Run flow steps with validate-gated apply and probes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.flow_registry import FlowDefinition, FlowStep, init_checklist_for_flow
from dragonclaw.installer import openclaw_installed
from dragonclaw.model_list import catalog_for_provider, models_list_probe_ok
from dragonclaw.openclaw_tools import run_models_list, run_models_set, run_models_status
from dragonclaw.openclaw_validate import run_openclaw_validate
from dragonclaw.flow_router import route_intent
from dragonclaw.presentation import (
    ENTER_MODEL_ID_MANUALLY,
    classify_global_menu_choice,
    run_dc_select,
    run_text_prompt,
    with_global_menu_rows,
)
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


def begin_flow(workspace_dir: Path, session: SessionState, flow: FlowDefinition) -> None:
    """Start or resume a flow without wiping probe-based checklist progress."""
    workspace_dir = workspace_dir.expanduser().resolve()
    if session.active_flow_id == flow.flow_id and session.flow_step_index > 0:
        _ensure_checklist(flow, session)
        return

    _ensure_checklist(flow, session)
    sync_checklist_from_probes(workspace_dir, flow, session)
    session.active_flow_id = flow.flow_id
    session.flow_step_index = first_incomplete_step(flow, workspace_dir, session)
    if session.flow_step_index >= len(flow.steps):
        if flow.flow_id == "flow.model.openrouter" and workspace_has_provider_auth(
            workspace_dir, "openrouter"
        ):
            if _read_config_primary(workspace_dir):
                session.flow_step_index = _step_index(flow, "models_probe")
            else:
                session.flow_step_index = _step_index(flow, "model_pick")
        else:
            session.flow_step_index = _step_index(flow, "api_key")


def sync_checklist_from_probes(
    workspace_dir: Path,
    flow: FlowDefinition,
    session: SessionState,
) -> None:
    """Mark checklist items done when workspace probes succeed."""
    if flow.flow_id != "flow.model.openrouter":
        return

    provider = "openrouter"
    if workspace_has_provider_auth(workspace_dir, provider):
        mark_checklist_item(
            session, "openrouter_auth", done=True, detail="already configured"
        )

    if workspace_has_provider_auth(workspace_dir, provider):
        result = run_models_list(workspace_dir, provider)
        if models_list_probe_ok(result):
            mark_checklist_item(
                session,
                "openrouter_models",
                done=True,
                detail="list OK",
            )

    primary = _read_config_primary(workspace_dir)
    if primary:
        session.flow_vars["primary_model"] = primary
        session.flow_vars["picked_model"] = primary
        mark_checklist_item(session, "openrouter_primary", done=True, detail=primary)


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
    import json

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


def _picked_model(session: SessionState, workspace_dir: Path) -> str:
    return session.flow_vars.get("picked_model") or _read_config_primary(workspace_dir)


def _step_satisfied(
    step: FlowStep,
    flow: FlowDefinition,
    workspace_dir: Path,
    session: SessionState,
) -> bool:
    if step.kind == "probe_install":
        return openclaw_installed()

    provider = step.provider or "openrouter"

    if step.step_id in {"api_key", "onboard"}:
        return workspace_has_provider_auth(workspace_dir, provider)

    if step.kind == "oc_json" and step.step_id == "model_list":
        item = _find_checklist_item(session, "openrouter_models")
        return item is not None and item.done

    if step.kind == "dc_menu" and step.step_id == "model_pick":
        return bool(_picked_model(session, workspace_dir))

    if step.kind == "oc_json" and step.step_id == "apply_primary":
        primary = _read_config_primary(workspace_dir)
        return bool(primary)

    if step.kind == "validate_probe":
        item = _find_checklist_item(session, "openrouter_primary")
        return item is not None and item.done

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
        if step.kind == "probe_install":
            if not openclaw_installed():
                return StepResult(
                    completed=False,
                    failed=True,
                    message="OpenClaw is not installed. Run: dragonclaw install --apply",
                )
            return StepResult(completed=True, message="OpenClaw is installed.")

        if step.kind == "dc_menu" and step.step_id == "api_key":
            provider = step.provider or "openrouter"
            if workspace_has_provider_auth(self.workspace_dir, provider):
                mark_checklist_item(
                    self.session, "openrouter_auth", done=True, detail="already configured"
                )
                return StepResult(completed=True, message="OpenRouter auth already present.")
            key = run_text_prompt(
                "OpenRouter API key\nPaste your key (sk-or-v1-…). Stored via openclaw onboard.",
                secret=True,
            )
            if not key.strip():
                return StepResult(completed=False, message="API key required to continue.")
            self.session.flow_vars["api_key"] = key.strip()
            return StepResult(completed=True)

        if step.kind == "dc_menu" and step.step_id == "model_pick":
            return self._run_model_pick(step)

        if step.kind == "oc_onboard":
            provider = step.provider or "openrouter"
            if workspace_has_provider_auth(self.workspace_dir, provider):
                mark_checklist_item(
                    self.session, "openrouter_auth", done=True, detail="already configured"
                )
                return StepResult(completed=True, message="OpenRouter auth already configured.")
            spec = load_provider_onboard_spec(provider)
            if spec is None:
                return StepResult(completed=False, failed=True, message=f"Unknown provider: {provider}")
            api_key = self.session.flow_vars.get("api_key", "")
            try:
                msg = run_provider_onboard_setup(self.workspace_dir, spec, api_key=api_key or None)
            except ValueError as exc:
                return StepResult(completed=False, failed=True, message=str(exc))
            mark_checklist_item(self.session, "openrouter_auth", done=True)
            return StepResult(completed=True, message=msg)

        if step.kind == "oc_json" and step.step_id == "model_list":
            provider = step.provider or "openrouter"
            result = run_models_list(self.workspace_dir, provider)
            if not models_list_probe_ok(result):
                return StepResult(
                    completed=False,
                    failed=True,
                    message=result.error or result.output or "models list failed",
                )
            mark_checklist_item(
                self.session,
                "openrouter_models",
                done=True,
                detail="list OK",
            )
            return StepResult(completed=True, message="OpenRouter models list reachable.")

        if step.kind == "oc_json" and step.step_id == "apply_primary":
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
            self.session.flow_vars["primary_model"] = primary
            mark_checklist_item(
                self.session,
                "openrouter_primary",
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
                if primary and primary not in status.output:
                    return StepResult(
                        completed=False,
                        failed=True,
                        message=f"Primary model {primary} not seen in models status.",
                    )
                if primary:
                    mark_checklist_item(
                        self.session,
                        "openrouter_primary",
                        done=True,
                        detail=primary,
                    )
            return StepResult(completed=True, message="Probes passed.")

        return StepResult(completed=False, failed=True, message=f"Unknown step kind: {step.kind}")

    def _handle_global_menu_choice(self, choice: str) -> StepResult | None:
        action = classify_global_menu_choice(choice)
        if action is None:
            return None
        if action == "quit":
            from dragonclaw.presentation import UserExit

            raise UserExit()
        if action == "back":
            return StepResult(completed=False, global_action="back", message="Back to hub.")
        if action == "ask":
            text = run_text_prompt("Ask DragonClaw")
            if not text.strip():
                return StepResult(completed=False, message="")
            routed = route_intent(text)
            if routed and routed.startswith("flow."):
                from dragonclaw.flow_registry import get_flow

                flow = get_flow(routed)
                if flow is not None:
                    begin_flow(self.workspace_dir, self.session, flow)
                    return StepResult(completed=False, global_action="ask", message=text.strip())
            return StepResult(completed=False, global_action="ask", message=text.strip())
        return None

    def _run_model_pick(self, step: FlowStep) -> StepResult:
        provider = step.provider or "openrouter"
        entries, catalog_detail = catalog_for_provider(self.workspace_dir, provider)
        if not entries:
            return StepResult(
                completed=False,
                failed=True,
                message=f"No models from OpenClaw ({catalog_detail}).",
            )

        label_to_id: dict[str, str] = {}
        content_labels: list[str] = []
        for entry in entries:
            label = entry.menu_label()
            content_labels.append(label)
            label_to_id[label] = entry.model_id

        content_labels.append(ENTER_MODEL_ID_MANUALLY)
        menu_labels = with_global_menu_rows(content_labels, in_flow=True)

        current_primary = _read_config_primary(self.workspace_dir)
        initial_index = 0
        if current_primary:
            for index, label in enumerate(menu_labels):
                if label_to_id.get(label) == current_primary:
                    initial_index = index
                    break

        choice = run_dc_select(
            f"Choose primary model ({catalog_detail})",
            menu_labels,
            initial_index=initial_index,
        )

        global_result = self._handle_global_menu_choice(choice)
        if global_result is not None:
            return global_result

        if choice == ENTER_MODEL_ID_MANUALLY:
            model_id = run_text_prompt("Model id (e.g. openrouter/anthropic/claude-sonnet-4)")
            if not model_id.strip():
                return StepResult(completed=False, message="Model selection cancelled.")
            picked = model_id.strip()
        else:
            picked = label_to_id.get(choice, choice)

        self.session.flow_vars["picked_model"] = picked
        return StepResult(completed=True, message=f"Selected {picked}.")
