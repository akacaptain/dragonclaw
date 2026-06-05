import json
from unittest.mock import patch

from dragonclaw.flow_engine import FlowEngine
from dragonclaw.flow_registry import get_flow
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.openclaw_validate import OpenClawValidationReport
from dragonclaw.session_store import SessionState


def test_openrouter_flow_install_missing(tmp_path):
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = SessionState(active_flow_id=flow.flow_id)
    engine = FlowEngine(tmp_path, session)
    with patch("dragonclaw.flow_engine.openclaw_installed", return_value=False):
        result = engine.run_flow(flow)
    assert result.failed
    assert "not installed" in result.message.lower()


def test_openrouter_flow_models_probe(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "openclaw.json").write_text(json.dumps({"agents": {"defaults": {}}}), encoding="utf-8")

    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=len(flow.steps) - 1,
        flow_vars={"primary_model": "openrouter/auto"},
    )

    engine = FlowEngine(workspace, session)
    with (
        patch("dragonclaw.flow_engine.openclaw_installed", return_value=True),
        patch(
            "dragonclaw.flow_engine.run_openclaw_validate",
            return_value=OpenClawValidationReport(ok=True),
        ),
        patch(
            "dragonclaw.flow_engine.run_models_status",
            return_value=ToolResult(name="status", ok=True, output="openrouter/auto ready"),
        ),
    ):
        result = engine.run_flow(flow)

    assert result.completed
    assert session.active_flow_id is None
    primary = next(item for item in session.checklist if item.id == "openrouter_primary")
    assert primary.done
