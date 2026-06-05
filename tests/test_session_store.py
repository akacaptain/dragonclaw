from dragonclaw.session_store import ChecklistItem, SessionState, load_session, save_session


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
