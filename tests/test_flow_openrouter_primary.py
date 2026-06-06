import json
from unittest.mock import patch

from dragonclaw.flow_engine import (
    FlowEngine,
    begin_flow,
    first_incomplete_step,
    primary_satisfies_openrouter_flow,
    refresh_hub_checklist,
    sync_checklist_from_probes,
)
from dragonclaw.flow_registry import get_flow, hub_next_hint, init_checklist_for_flow
from dragonclaw.model_list import (
    MIN_LIVE_CATALOG_MODELS,
    ModelCatalogEntry,
    models_catalog_sufficient,
)
from dragonclaw.openclaw_tools import ToolResult
from dragonclaw.session_store import ChecklistItem, SessionState


def _openrouter_flow():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    return flow


def _write_primary(workspace, primary: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "openclaw.json").write_text(
        json.dumps({"agents": {"defaults": {"model": {"primary": primary}}}}),
        encoding="utf-8",
    )


def test_primary_satisfies_openrouter_flow():
    assert primary_satisfies_openrouter_flow("openrouter/auto")
    assert not primary_satisfies_openrouter_flow("anthropic/claude-opus-4-8")


def test_anthropic_primary_does_not_jump_to_models_probe(tmp_path):
    workspace = tmp_path / "ws"
    _write_primary(workspace, "anthropic/claude-opus-4-8")
    flow = _openrouter_flow()
    session = SessionState(checklist=init_checklist_for_flow(flow))

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch("dragonclaw.flow_engine.openclaw_installed", return_value=True),
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(
                [ModelCatalogEntry(model_id="openrouter/auto")],
                "OpenClaw CLI catalog (3 models)",
            ),
        ),
    ):
        begin_flow(workspace, session, flow)

    models_probe_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "models_probe")
    assert session.flow_step_index != models_probe_index
    model_list_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_list")
    assert session.flow_step_index == model_list_index


def test_first_incomplete_step_anthropic_lands_before_model_pick(tmp_path):
    workspace = tmp_path / "ws"
    _write_primary(workspace, "anthropic/claude-opus-4-8")
    flow = _openrouter_flow()
    session = SessionState(checklist=init_checklist_for_flow(flow))

    with patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True):
        index = first_incomplete_step(flow, workspace, session)

    model_list_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_list")
    assert index == model_list_index


def test_sync_checklist_non_or_primary_open(tmp_path):
    workspace = tmp_path / "ws"
    _write_primary(workspace, "anthropic/claude-opus-4-8")
    flow = _openrouter_flow()
    session = SessionState(checklist=init_checklist_for_flow(flow))

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(
                [ModelCatalogEntry(model_id="openrouter/auto")],
                "test",
            ),
        ),
    ):
        sync_checklist_from_probes(workspace, flow, session)

    primary = next(item for item in session.checklist if item.id == "openrouter_primary")
    assert not primary.done
    assert "not openrouter" in primary.detail.lower()


def test_flow_runs_model_pick_not_probe_only(tmp_path):
    workspace = tmp_path / "ws"
    _write_primary(workspace, "anthropic/claude-opus-4-8")
    flow = _openrouter_flow()
    model_pick_index = next(i for i, s in enumerate(flow.steps) if s.step_id == "model_pick")
    session = SessionState(
        active_flow_id=flow.flow_id,
        flow_step_index=model_pick_index,
        checklist=init_checklist_for_flow(flow),
    )

    entries = [ModelCatalogEntry(model_id="openrouter/auto", display_name="Auto")]
    engine = FlowEngine(workspace, session)
    with (
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(entries, "dc"),
        ),
        patch(
            "dragonclaw.flow_engine.run_dc_select",
            return_value=entries[0].menu_label(),
        ),
    ):
        result = engine._run_step(flow, flow.steps[model_pick_index])

    assert result.completed
    assert not result.failed
    assert session.flow_vars["picked_model"] == "openrouter/auto"


def test_hub_refresh_clears_stale_list_ok(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    flow = _openrouter_flow()
    session = SessionState(
        checklist=[
            ChecklistItem(
                id="openrouter_auth",
                label="OpenRouter API key configured",
                done=True,
            ),
            ChecklistItem(
                id="openrouter_models",
                label="OpenRouter models reachable",
                done=True,
                detail="list OK",
            ),
            ChecklistItem(
                id="openrouter_primary",
                label="Primary model set and probed",
                done=False,
            ),
        ],
    )

    with (
        patch("dragonclaw.flow_engine.workspace_has_provider_auth", return_value=True),
        patch(
            "dragonclaw.flow_engine.catalog_for_provider",
            return_value=(
                [ModelCatalogEntry(model_id="openrouter/auto")],
                "test",
            ),
        ),
    ):
        refresh_hub_checklist(workspace, session)

    models = next(item for item in session.checklist if item.id == "openrouter_models")
    assert not models.done
    assert "1 models" in models.detail


def test_models_done_derived_from_count_only():
    assert not models_catalog_sufficient(3)
    assert models_catalog_sufficient(MIN_LIVE_CATALOG_MODELS)


def test_hub_next_hint_non_openrouter_primary(tmp_path):
    workspace = tmp_path / "ws"
    _write_primary(workspace, "anthropic/claude-opus-4-8")
    session = SessionState(checklist=init_checklist_for_flow(_openrouter_flow()))

    hint = hub_next_hint(session, workspace_dir=workspace)
    assert hint is not None
    assert "anthropic/claude-opus-4-8" in hint
