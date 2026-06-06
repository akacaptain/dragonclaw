import json
from unittest.mock import patch

from dragonclaw.flow_engine import FlowEngine, begin_flow
from dragonclaw.flow_registry import get_flow, init_checklist_for_flow
from dragonclaw.model_list import ModelCatalogEntry
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.presentation import ENTER_MODEL_ID_MANUALLY
from dragonclaw.session_store import SessionState


def _openrouter_flow():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    return flow


def test_openrouter_flow_model_pick_is_dc_menu():
    flow = _openrouter_flow()
    step = next(s for s in flow.steps if s.step_id == "model_pick")
    assert step.kind == "dc_menu"
    assert "oc_interactive" not in [s.kind for s in flow.steps]


def test_model_pick_dc_menu_select(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
        flow_vars={"api_key": "sk-or-v1-test"},
    )

    entries = [
        ModelCatalogEntry(model_id="openrouter/auto", display_name="OpenRouter Auto"),
    ]
    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(entries, "DragonClaw live catalog (1 models)"),
        ),
        patch(
            "dragonclaw.flow_engine.run_dc_select",
            return_value=entries[0].menu_label(),
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    assert result.completed
    assert session.flow_vars["picked_model"] == "openrouter/auto"


def test_model_pick_manual_id(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )

    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=([], "API key not found"),
        ),
        patch(
            "dragonclaw.flow_engine.run_text_prompt",
            return_value="openrouter/auto",
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    assert result.completed
    assert session.flow_vars["picked_model"] == "openrouter/auto"


def test_model_pick_manual_menu_option(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )
    entries = [
        ModelCatalogEntry(model_id="openrouter/auto", display_name="OpenRouter Auto"),
    ]

    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(entries, "DragonClaw live catalog (1 models)"),
        ),
        patch(
            "dragonclaw.flow_engine.run_dc_select",
            return_value=ENTER_MODEL_ID_MANUALLY,
        ),
        patch(
            "dragonclaw.flow_engine.run_text_prompt",
            return_value="auto",
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    assert result.completed
    assert session.flow_vars["picked_model"] == "openrouter/auto"


def test_apply_primary_models_set(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "apply_primary")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
        flow_vars={"picked_model": "openrouter/auto"},
    )

    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.run_models_set",
            return_value=ToolResult(name="models set", ok=True, output="ok"),
        ) as mock_set,
        patch(
            "dragonclaw.flow_engine._read_config_primary",
            side_effect=["", "openrouter/auto"],
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    mock_set.assert_called_once_with(workspace, "openrouter/auto")
    assert result.completed
    primary = next(item for item in session.checklist if item.id == "openrouter_primary")
    assert primary.done
