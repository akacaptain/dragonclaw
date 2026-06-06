from unittest.mock import patch

import pytest

from dragonclaw.chat_loop import run_chat_loop
from dragonclaw.flow_registry import list_flows
from dragonclaw.presentation import (
    ASK_DRAGONCLAW_OPTION,
    FLOW_PAUSE_HUB,
    QUIT_OPTION,
    UserExit,
    with_global_menu_rows,
)


def test_hub_select_includes_registered_flows_and_globals(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    expected_labels = with_global_menu_rows(
        [flow.label for flow in list_flows()],
        in_flow=False,
    )

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup", side_effect=lambda s: s),
        patch("dragonclaw.chat_loop.save_session"),
        patch("dragonclaw.chat_loop.run_dc_select", return_value=QUIT_OPTION) as mock_select,
    ):
        from dragonclaw.session_store import SessionState

        mock_load.return_value = SessionState()
        run_chat_loop(workspace)

    mock_select.assert_called_once()
    assert mock_select.call_args[0][1] == expected_labels
    assert "Validate config" not in expected_labels


def test_hub_pick_runs_flow_when_oc_installed(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup", side_effect=lambda s: s),
        patch("dragonclaw.chat_loop.save_session"),
        patch("dragonclaw.installer.openclaw_installed", return_value=True),
        patch("dragonclaw.chat_loop.get_flow") as mock_get_flow,
        patch("dragonclaw.chat_loop.FlowEngine") as mock_engine_cls,
        patch("dragonclaw.chat_loop.begin_flow") as mock_begin,
        patch(
            "dragonclaw.chat_loop.run_flow_pause_menu",
            return_value=QUIT_OPTION,
        ),
        patch(
            "dragonclaw.chat_loop.run_dc_select",
            side_effect=["Setup OpenRouter", QUIT_OPTION],
        ),
    ):
        from dragonclaw.flow_engine import StepResult
        from dragonclaw.session_store import SessionState

        session = SessionState()

        def _begin(workspace, state, flow):
            state.active_flow_id = "flow.model.openrouter"
            state.flow_step_index = 1

        mock_begin.side_effect = _begin
        mock_load.return_value = session
        mock_get_flow.return_value = object()
        mock_engine_cls.return_value.run_flow.return_value = StepResult(
            completed=False,
            message="step",
        )
        run_chat_loop(workspace)

    mock_begin.assert_called_once()
    mock_engine_cls.assert_called_once()


def test_hub_default_when_oc_installed_and_active_flow(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup") as mock_prepare,
        patch("dragonclaw.chat_loop.save_session"),
        patch("dragonclaw.chat_loop.FlowEngine") as mock_engine_cls,
        patch("dragonclaw.chat_loop.run_dc_select", return_value=QUIT_OPTION) as mock_select,
    ):
        from dragonclaw.session_store import SessionState

        session = SessionState(active_flow_id="flow.model.openrouter", flow_step_index=3)
        mock_load.return_value = session
        mock_prepare.return_value = SessionState(checklist=session.checklist)
        run_chat_loop(workspace)

    mock_engine_cls.assert_not_called()
    mock_select.assert_called_once()


def test_resume_flow_when_oc_not_installed(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup", side_effect=lambda s: s),
        patch("dragonclaw.chat_loop.save_session"),
        patch("dragonclaw.installer.openclaw_installed", return_value=False),
        patch("dragonclaw.chat_loop.get_flow") as mock_get_flow,
        patch("dragonclaw.chat_loop.FlowEngine") as mock_engine_cls,
        patch(
            "dragonclaw.chat_loop.run_flow_pause_menu",
            return_value=QUIT_OPTION,
        ),
        patch(
            "dragonclaw.chat_loop.run_dc_select",
            return_value=QUIT_OPTION,
        ),
    ):
        from dragonclaw.flow_engine import StepResult
        from dragonclaw.session_store import SessionState

        session = SessionState(active_flow_id="flow.model.openrouter", flow_step_index=1)
        mock_load.return_value = session
        mock_get_flow.return_value = object()
        mock_engine_cls.return_value.run_flow.return_value = StepResult(
            completed=False,
            message="need api key",
        )
        run_chat_loop(workspace)

    mock_engine_cls.assert_called_once()


def test_chat_loop_user_exit_saves_and_stops(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup", side_effect=lambda s: s),
        patch("dragonclaw.chat_loop.save_session") as mock_save,
        patch(
            "dragonclaw.chat_loop.run_dc_select",
            return_value=QUIT_OPTION,
        ),
    ):
        from dragonclaw.session_store import SessionState

        mock_load.return_value = SessionState()
        run_chat_loop(workspace)

    assert mock_save.call_count >= 1


def test_hub_ask_dragonclaw_routes_to_llm(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup", side_effect=lambda s: s),
        patch("dragonclaw.chat_loop.save_session"),
        patch(
            "dragonclaw.chat_loop.run_dc_select",
            side_effect=[ASK_DRAGONCLAW_OPTION, QUIT_OPTION],
        ),
        patch("dragonclaw.chat_loop.run_text_prompt", return_value="setup openrouter"),
        patch("dragonclaw.chat_loop.route_intent", return_value="flow.model.openrouter"),
        patch("dragonclaw.chat_loop.get_flow") as mock_get_flow,
        patch("dragonclaw.chat_loop.begin_flow") as mock_begin,
    ):
        from dragonclaw.session_store import SessionState

        mock_load.return_value = SessionState()
        mock_get_flow.return_value = object()
        run_chat_loop(workspace)

    mock_begin.assert_called_once()


def test_flow_pause_back_to_hub(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with (
        patch("dragonclaw.chat_loop.load_session") as mock_load,
        patch("dragonclaw.chat_loop.prepare_session_startup", side_effect=lambda s: s),
        patch("dragonclaw.chat_loop.save_session"),
        patch("dragonclaw.installer.openclaw_installed", return_value=False),
        patch("dragonclaw.chat_loop.get_flow") as mock_get_flow,
        patch("dragonclaw.chat_loop.FlowEngine") as mock_engine_cls,
        patch(
            "dragonclaw.chat_loop.run_flow_pause_menu",
            return_value=FLOW_PAUSE_HUB,
        ),
        patch(
            "dragonclaw.chat_loop.run_dc_select",
            return_value=QUIT_OPTION,
        ),
    ):
        from dragonclaw.flow_engine import StepResult
        from dragonclaw.session_store import SessionState

        session = SessionState(active_flow_id="flow.model.openrouter", flow_step_index=3)
        mock_load.return_value = session
        mock_get_flow.return_value = object()
        mock_engine_cls.return_value.run_flow.return_value = StepResult(
            completed=False,
            failed=True,
            message="models set failed",
        )
        run_chat_loop(workspace)

    assert session.active_flow_id is None
