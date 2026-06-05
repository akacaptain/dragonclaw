import json
from unittest.mock import patch

from dragonclaw.flow_engine import (
    FlowEngine,
    begin_flow,
    first_incomplete_step,
    sync_checklist_from_probes,
)
from dragonclaw.flow_registry import get_flow, init_checklist_for_flow
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.session_store import ChecklistItem, SessionState


def _openrouter_flow():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    return flow


def test_begin_flow_preserves_auth_checklist(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    session = SessionState(
        checklist=init_checklist_for_flow(flow),
        flow_step_index=0,
    )
    for item in session.checklist:
        if item.id == "openrouter_auth":
            item.done = True
            item.detail = "already configured"

    with patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True):
        begin_flow(workspace, session, flow)

    auth = next(item for item in session.checklist if item.id == "openrouter_auth")
    assert auth.done
    assert auth.detail == "already configured"


def test_begin_flow_skips_to_model_list_when_auth_done(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    session = SessionState()

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch("dragonclaw.flow_engine.openclaw_installed", return_value=True),
        patch(
            "dragonclaw.flow_engine.run_models_list",
            return_value=ToolResult(name="models", ok=False, output="", error="not configured"),
        ),
    ):
        begin_flow(workspace, session, flow)

    model_list_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_list")
    assert session.flow_step_index == model_list_index


def test_oc_onboard_skipped_when_auth_exists(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    onboard_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "onboard")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=onboard_index,
        checklist=init_checklist_for_flow(flow),
    )

    engine = FlowEngine(workspace, session)
    step = flow.steps[onboard_index]
    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch("dragonclaw.flow_engine.run_provider_onboard_setup") as mock_onboard,
    ):
        result = engine._run_step(flow, step)

    mock_onboard.assert_not_called()
    assert result.completed
    assert not result.failed
    auth = next(item for item in session.checklist if item.id == "openrouter_auth")
    assert auth.done


def test_api_key_step_blocks_without_clearing_active_flow(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    api_key_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "api_key")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=api_key_index,
        checklist=init_checklist_for_flow(flow),
    )

    engine = FlowEngine(workspace, session)
    with (
        patch("dragonclaw.flow_engine.openclaw_installed", return_value=True),
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=False),
        patch("dragonclaw.flow_engine.run_text_prompt", return_value=""),
    ):
        result = engine.run_flow(flow)

    assert not result.completed
    assert not result.failed
    assert session.active_flow_id == flow.flow_id
    assert session.flow_step_index == api_key_index


def test_sync_checklist_marks_primary_from_config(tmp_path):
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
    session = SessionState(checklist=init_checklist_for_flow(flow))

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch(
            "dragonclaw.flow_engine.run_models_list",
            return_value=ToolResult(
                name="models",
                ok=True,
                output='{"models":[{"key":"openrouter/auto"}]}',
            ),
        ),
    ):
        sync_checklist_from_probes(workspace, flow, session)

    primary = next(item for item in session.checklist if item.id == "openrouter_primary")
    assert primary.done
    assert session.flow_vars.get("primary_model") == "openrouter/auto"
    models = next(item for item in session.checklist if item.id == "openrouter_models")
    assert models.detail == "list OK"


def test_checklist_labels_refresh_on_begin_flow(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    session = SessionState(
        checklist=[
            ChecklistItem(
                id="openrouter_models",
                label="Live OpenRouter model list — 3 models",
                done=True,
                detail="stale",
            ),
            ChecklistItem(
                id="openrouter_auth",
                label="OpenRouter API key configured",
            ),
            ChecklistItem(
                id="openrouter_primary",
                label="Primary model set via OpenClaw configure",
            ),
        ],
    )

    with patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=False):
        begin_flow(workspace, session, flow)

    models = next(item for item in session.checklist if item.id == "openrouter_models")
    assert models.label == "OpenRouter models reachable"
    primary = next(item for item in session.checklist if item.id == "openrouter_primary")
    assert primary.label == "Primary model set and probed"


def test_first_incomplete_step_after_primary_in_config(tmp_path):
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
    session = SessionState(
        checklist=init_checklist_for_flow(flow),
        flow_vars={"primary_model": "openrouter/auto"},
    )
    for item in session.checklist:
        if item.id in {"openrouter_auth", "openrouter_models"}:
            item.done = True

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch("dragonclaw.flow_engine.openclaw_installed", return_value=True),
    ):
        index = first_incomplete_step(flow, workspace, session)

    validate_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "models_probe")
    assert index == validate_index
