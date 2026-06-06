"""Legacy oc_interactive model handoff removed — kept file for apply_primary / model_list tests."""

import json
from unittest.mock import patch

from dragonclaw.flow_engine import FlowEngine, begin_flow
from dragonclaw.flow_registry import get_flow, init_checklist_for_flow
from dragonclaw.model_list import ModelCatalogEntry
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.session_store import SessionState


def _openrouter_flow():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    return flow


def test_apply_primary_skips_when_config_already_has_primary(tmp_path):
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
        ) as mock_set,
        patch(
            "dragonclaw.flow_engine._read_config_primary",
            return_value="openrouter/auto",
        ),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    mock_set.assert_not_called()
    assert result.completed
    assert "already set" in result.message


def test_model_list_probe_marks_checklist(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    step_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_list")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=step_index,
        checklist=init_checklist_for_flow(flow),
    )

    entries = [ModelCatalogEntry(model_id="openrouter/auto", display_name="Auto")]
    engine = FlowEngine(workspace, session)
    with patch(
        "dragonclaw.flow_engine.catalog_for_provider",
        return_value=(entries, "OpenClaw CLI catalog (1 models)"),
    ):
        result = engine._run_step(flow, flow.steps[step_index])

    assert result.completed
    models_item = next(item for item in session.checklist if item.id == "openrouter_models")
    assert not models_item.done
    assert "1 models" in models_item.detail


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
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=([ModelCatalogEntry(model_id="openrouter/auto")], "dc"),
        ),
    ):
        begin_flow(workspace, session, flow)

    validate_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "models_probe")
    assert session.flow_step_index == validate_index
