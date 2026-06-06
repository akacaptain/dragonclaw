from pathlib import Path
from unittest.mock import patch

from dragonclaw.model_list import (
    MIN_LIVE_CATALOG_MODELS,
    ModelCatalogEntry,
    catalog_for_provider,
    format_models_probe_detail,
    models_catalog_sufficient,
    models_list_count,
    models_list_probe_ok,
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


def test_catalog_prefers_dc_adapter(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dc_entries = [
        ModelCatalogEntry(model_id=f"openrouter/model-{index}", display_name=f"Model {index}")
        for index in range(200)
    ]
    with (
        patch(
            "dragonclaw.dc_catalog.fetch_dc_catalog",
            return_value=(dc_entries, "DragonClaw live catalog (200 models)"),
        ) as mock_dc,
        patch("dragonclaw.model_list.run_picker_catalog") as mock_picker,
        patch("dragonclaw.model_list.run_models_list") as mock_list,
    ):
        entries, detail = catalog_for_provider(workspace, "openrouter")

    mock_dc.assert_called_once()
    mock_picker.assert_not_called()
    mock_list.assert_not_called()
    assert len(entries) == 200
    assert "DragonClaw" in detail


def test_catalog_prefers_picker_when_dc_empty(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with (
        patch(
            "dragonclaw.dc_catalog.fetch_dc_catalog",
            return_value=([], "API key not found"),
        ),
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
            "dragonclaw.dc_catalog.fetch_dc_catalog",
            return_value=([], "no DC adapter"),
        ),
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


def test_models_list_count_and_thin_catalog_detail():
    raw = '{"count": 3, "models": [{"key": "openrouter/auto"}]}'
    result = ToolResult(name="models", ok=True, output=raw)
    assert models_list_probe_ok(result)
    assert models_list_count(result) == 3
    assert not models_catalog_sufficient(3)
    assert models_catalog_sufficient(MIN_LIVE_CATALOG_MODELS)
    detail = format_models_probe_detail(3)
    assert "3 models" in detail
    assert "thin catalog" in detail


def test_catalog_for_provider_generic(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    groq_json = '{"models": [{"key": "llama-3.3-70b-versatile", "name": "Llama 3.3"}]}'
    with (
        patch(
            "dragonclaw.dc_catalog.fetch_dc_catalog",
            return_value=([], "no DC adapter"),
        ),
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
