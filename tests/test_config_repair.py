import json
from unittest.mock import patch

from dragonclaw.config_apply import REMOVE_KEYS_FIELD, apply_patch_to_document
from dragonclaw.config_repair import collect_invalid_top_level_keys
from dragonclaw.openclaw_validate import OpenClawValidationReport


def test_apply_remove_keys():
    current = {"provider": "openrouter", "agents": {"defaults": {}}}
    merged = apply_patch_to_document(current, {REMOVE_KEYS_FIELD: ["provider"]})
    assert "provider" not in merged
    assert "agents" in merged


def test_collect_invalid_top_level_keys_detects_provider(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "openclaw.json").write_text(
        json.dumps({"provider": "openrouter", "agents": {}}),
        encoding="utf-8",
    )

    mock_report = OpenClawValidationReport(ok=False, unrecognized_keys=["provider"])
    with patch("dragonclaw.config_repair.run_openclaw_validate", return_value=mock_report):
        keys, detail = collect_invalid_top_level_keys(workspace)

    assert keys == ["provider"]
    assert "provider" in detail
