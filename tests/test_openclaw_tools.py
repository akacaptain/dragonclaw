import json
from unittest.mock import patch

from dragonclaw.openclaw_tools import ToolResult, build_tool_context, execute_command, probe_workspace
from dragonclaw.openclaw_validate import OpenClawValidationReport


def test_probe_workspace_reports_parse_error(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "openclaw.json").write_text('{"bad": }', encoding="utf-8")

    snapshot = probe_workspace(workspace)
    assert "openclaw.json_parse_error" in snapshot
    assert snapshot["config_health"]["json_parse_error"]


def test_execute_command_dry_run(tmp_path):
    result = execute_command(tmp_path, ["doctor"], dry_run=True)
    assert result.ok is True
    assert "Dry run" in result.output


def test_build_tool_context_mocks_cli(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "openclaw.json").write_text(json.dumps({"agents": {}}), encoding="utf-8")

    with (
        patch(
            "dragonclaw.openclaw_tools.run_openclaw_validate",
            return_value=OpenClawValidationReport(ok=True),
        ),
        patch(
            "dragonclaw.openclaw_tools.run_doctor",
            return_value=ToolResult(name="doctor", ok=True, output="all good"),
        ),
        patch(
            "dragonclaw.openclaw_tools.run_openclaw_version",
            return_value=ToolResult(name="version", ok=True, output="OpenClaw 2026.6.1"),
        ),
    ):
        ctx = build_tool_context(workspace, include_doctor=True)

    assert ctx["openclaw_validate"]["ok"] is True
    assert "openclaw_doctor" in ctx
