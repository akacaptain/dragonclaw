import json
from unittest.mock import patch

from dragonclaw.flow_engine import FlowEngine, begin_flow
from dragonclaw.flow_registry import get_flow, init_checklist_for_flow
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.presentation import (
    ASK_DRAGONCLAW_OPTION,
    ENTER_MODEL_ID_MANUALLY,
    FLOW_PAUSE_HUB,
    QUIT_OPTION,
    with_global_menu_rows,
)
from dragonclaw.session_store import SessionState


def _openrouter_flow():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    return flow


def test_openrouter_flow_has_model_pick_not_configure():
    flow = _openrouter_flow()
    step_ids = [step.step_id for step in flow.steps]
    assert "model_pick" in step_ids
    assert "apply_primary" in step_ids
    assert "model_configure" not in step_ids
    assert all(step.kind != "oc_interactive" for step in flow.steps)


def test_model_pick_uses_select_not_configure(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )
    from dragonclaw.model_list import ModelCatalogEntry

    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(
                [ModelCatalogEntry(model_id="openrouter/auto", display_name="OpenRouter Auto")],
                "OpenClaw CLI catalog (1 models)",
            ),
        ),
        patch(
            "dragonclaw.flow_engine.run_dc_select",
            return_value="OpenRouter Auto — openrouter/auto",
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
            return_value="openrouter/auto",
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    mock_set.assert_called_once_with(workspace, "openrouter/auto")
    assert result.completed
    primary = next(item for item in session.checklist if item.id == "openrouter_primary")
    assert primary.done


def test_model_list_probe_marks_checklist_without_count_hype(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_list")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )

    engine = FlowEngine(workspace, session)
    sparse_json = json.dumps(
        {
            "count": 3,
            "models": [
                {"key": "openrouter/auto", "name": "OpenRouter Auto"},
            ],
        }
    )
    with patch(
        "dragonclaw.flow_engine.run_models_list",
        return_value=ToolResult(name="models", ok=True, output=sparse_json),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    assert result.completed
    models_item = next(item for item in session.checklist if item.id == "openrouter_models")
    assert models_item.detail == "list OK"
    assert "3 models" not in models_item.detail


def test_begin_flow_skips_model_pick_when_primary_set(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "openclaw.json").write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "model": {"primary": "openrouter/auto"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    flow = _openrouter_flow()
    session = SessionState()
    for item in init_checklist_for_flow(flow):
        if item.id in {"openrouter_auth", "openrouter_models"}:
            item.done = True

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch("dragonclaw.flow_engine.openclaw_installed", return_value=True),
        patch(
            "dragonclaw.flow_engine.run_models_list",
            return_value=ToolResult(
                name="models",
                ok=True,
                output='{"models":[{"key":"openrouter/auto"}]}',
            ),
        ),
    ):
        begin_flow(workspace, session, flow)

    validate_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "models_probe")
    assert session.flow_step_index == validate_index


def test_global_menu_rows_on_model_pick(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )
    from dragonclaw.model_list import ModelCatalogEntry

    engine = FlowEngine(workspace, session)
    content = ["OpenRouter Auto — openrouter/auto", ENTER_MODEL_ID_MANUALLY]
    expected_menu = with_global_menu_rows(content, in_flow=True)

    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(
                [ModelCatalogEntry(model_id="openrouter/auto", display_name="OpenRouter Auto")],
                "OpenClaw picker catalog (1 models)",
            ),
        ),
        patch("dragonclaw.flow_engine.run_dc_select") as mock_select,
        patch("dragonclaw.flow_engine.run_text_prompt", return_value="setup openrouter"),
        patch("dragonclaw.flow_engine.route_intent", return_value=None),
    ):
        mock_select.return_value = ASK_DRAGONCLAW_OPTION
        result = engine._run_step(flow, flow.steps[step_index])

    mock_select.assert_called_once()
    assert mock_select.call_args[0][1] == expected_menu
    assert result.global_action == "ask"
    assert not result.completed


def test_model_pick_manual_entry(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )
    from dragonclaw.model_list import ModelCatalogEntry

    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(
                [ModelCatalogEntry(model_id="openrouter/auto")],
                "OpenClaw CLI catalog (1 models)",
            ),
        ),
        patch("dragonclaw.flow_engine.run_dc_select", return_value=ENTER_MODEL_ID_MANUALLY),
        patch(
            "dragonclaw.flow_engine.run_text_prompt",
            return_value="openrouter/custom/model",
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    assert result.completed
    assert session.flow_vars["picked_model"] == "openrouter/custom/model"
