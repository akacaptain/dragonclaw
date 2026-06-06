from unittest.mock import patch

from dragonclaw.session_store import (
    ChecklistItem,
    SessionState,
    load_session,
    prepare_session_startup,
    save_session,
    should_resume_session,
)


def test_session_roundtrip(tmp_path):
    state = SessionState(
        active_flow_id="flow.model.openrouter",
        flow_step_index=2,
        checklist=[ChecklistItem(id="openrouter_auth", label="Auth", done=True, detail="ok")],
        flow_vars={"api_key": "redacted"},
    )
    save_session(tmp_path, state)
    loaded = load_session(tmp_path)
    assert loaded.active_flow_id == "flow.model.openrouter"
    assert loaded.flow_step_index == 2
    assert loaded.checklist[0].done is True


def test_should_resume_when_oc_not_installed():
    session = SessionState(active_flow_id="flow.model.openrouter", flow_step_index=2)
    with patch("dragonclaw.installer.openclaw_installed", return_value=False):
        assert should_resume_session(session) is True


def test_should_not_resume_when_oc_installed():
    session = SessionState(active_flow_id="flow.model.openrouter", flow_step_index=2)
    with patch("dragonclaw.installer.openclaw_installed", return_value=True):
        assert should_resume_session(session) is False


def test_prepare_session_startup_clears_active_flow_when_oc_installed():
    session = SessionState(
        active_flow_id="flow.model.openrouter",
        flow_step_index=4,
    )
    with patch("dragonclaw.installer.openclaw_installed", return_value=True):
        prepared = prepare_session_startup(session)

    assert prepared.active_flow_id is None
    assert prepared.flow_step_index == 0


def test_prepare_session_startup_keeps_active_flow_when_oc_missing():
    session = SessionState(
        active_flow_id="flow.model.openrouter",
        flow_step_index=2,
    )
    with patch("dragonclaw.installer.openclaw_installed", return_value=False):
        prepared = prepare_session_startup(session)

    assert prepared.active_flow_id == "flow.model.openrouter"
    assert prepared.flow_step_index == 2
