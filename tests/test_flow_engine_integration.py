"""Opt-in live OpenClaw flow probes."""

from __future__ import annotations

import pytest

from dragonclaw.openclaw_tools import run_models_list, run_openclaw_version
from dragonclaw.provider_onboard import workspace_has_provider_auth


@pytest.mark.real_openclaw_cli
def test_live_openclaw_version():
    from dragonclaw.bootstrap import default_workspace_dir

    ws = default_workspace_dir()
    result = run_openclaw_version(ws)
    if result.output:
        assert "2026." in result.output


@pytest.mark.real_openclaw_cli
def test_live_openrouter_auth_and_models_if_configured():
    from dragonclaw.bootstrap import default_workspace_dir

    ws = default_workspace_dir()
    if not workspace_has_provider_auth(ws, "openrouter"):
        pytest.skip("OpenRouter not configured in workspace")
    result = run_models_list(ws, "openrouter")
    assert result.ok, result.error or result.output
    assert result.output.strip()
