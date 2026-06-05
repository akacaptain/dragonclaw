from pathlib import Path
from unittest.mock import patch

from dragonclaw.model_list import (
    ModelCatalogEntry,
    catalog_for_provider,
    normalize_model_key,
    parse_models_list_entries,
    parse_models_list_json,
)
from dragonclaw.openclaw_tools import ToolResult


def test_parse_models_list_json():
    raw = '{"models": ["openrouter/auto", "openrouter/anthropic/claude-3.5-sonnet"]}'
    assert parse_models_list_json(raw) == [
        "openrouter/auto",
        "openrouter/anthropic/claude-3.5-sonnet",
    ]


def test_parse_models_list_object_ids():
    raw = '{"models": [{"id": "openrouter/foo"}, {"model": "openrouter/bar"}]}'
    assert parse_models_list_json(raw) == ["openrouter/foo", "openrouter/bar"]


def test_parse_models_list_key_and_name():
    raw = '{"models": [{"key": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4"}]}'
    entries = parse_models_list_entries(raw, "openrouter")
    assert len(entries) == 1
    assert entries[0].model_id == "openrouter/anthropic/claude-sonnet-4"
    assert entries[0].display_name == "Claude Sonnet 4"
    assert "Claude Sonnet 4" in entries[0].menu_label()


def test_normalize_model_key():
    assert normalize_model_key("anthropic/claude", "openrouter") == "openrouter/anthropic/claude"
    assert normalize_model_key("openrouter/auto", "openrouter") == "openrouter/auto"


def _picker_payload(count: int) -> str:
    models = [
        {"key": f"openrouter/model-{index}", "name": f"Model {index}"}
        for index in range(count)
    ]
    import json

    return json.dumps({"ok": True, "source": "picker_catalog", "models": models})


def test_catalog_prefers_picker_bridge(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with (
        patch(
            "dragonclaw.model_list.run_picker_catalog",
            return_value=ToolResult(name="picker_catalog", ok=True, output=_picker_payload(200)),
        ) as mock_picker,
        patch("dragonclaw.model_list.run_models_list") as mock_list,
    ):
        entries, detail = catalog_for_provider(workspace, "openrouter")

    mock_picker.assert_called_once_with(workspace, "openrouter")
    mock_list.assert_not_called()
    assert len(entries) == 200
    assert "OpenClaw picker catalog" in detail


def test_catalog_fallback_to_models_list(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    groq_json = '{"models": [{"key": "llama-3.3-70b-versatile", "name": "Llama 3.3"}]}'
    with (
        patch(
            "dragonclaw.model_list.run_picker_catalog",
            return_value=ToolResult(
                name="picker_catalog",
                ok=False,
                output="",
                error="openclaw dist directory not found",
            ),
        ),
        patch(
            "dragonclaw.model_list.run_models_list",
            return_value=ToolResult(name="models", ok=True, output=groq_json),
        ) as mock_list,
    ):
        entries, detail = catalog_for_provider(workspace, "groq")

    mock_list.assert_called_once_with(workspace, "groq")
    assert len(entries) == 1
    assert entries[0].model_id == "groq/llama-3.3-70b-versatile"
    assert "OpenClaw CLI catalog" in detail


def test_catalog_for_provider_generic(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    groq_json = '{"models": [{"key": "llama-3.3-70b-versatile", "name": "Llama 3.3"}]}'
    with (
        patch(
            "dragonclaw.model_list.run_picker_catalog",
            return_value=ToolResult(name="picker_catalog", ok=False, output="", error="no dist"),
        ),
        patch(
            "dragonclaw.model_list.run_models_list",
            return_value=ToolResult(name="models", ok=True, output=groq_json),
        ) as mock_list,
    ):
        entries, detail = catalog_for_provider(workspace, "groq")

    mock_list.assert_called_once_with(workspace, "groq")
    assert len(entries) == 1
    assert entries[0].model_id == "groq/llama-3.3-70b-versatile"
    assert "OpenClaw CLI catalog" in detail
