from dragonclaw.flow_registry import (
    get_flow,
    hub_label_for_flow,
    hub_labels_for_session,
    hub_next_hint,
    resolve_flow_id_from_hub_label,
)
from dragonclaw.session_store import ChecklistItem, SessionState


def _openrouter_session(**kwargs) -> SessionState:
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = SessionState(
        checklist=[
            ChecklistItem(id=item_id, label=label)
            for item_id, label in flow.checklist
        ],
        **kwargs,
    )
    return session


def test_hub_label_default_when_checklist_empty():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = SessionState()
    assert hub_label_for_flow(flow, session) == "Setup OpenRouter"


def test_hub_label_set_primary_when_auth_done():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = _openrouter_session()
    session.checklist[0].done = True
    session.checklist[1].done = True
    assert hub_label_for_flow(flow, session) == "Set primary model (OpenRouter)"


def test_hub_label_thin_catalog_when_models_open():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = _openrouter_session()
    session.checklist[0].done = True
    session.checklist[1].done = False
    session.checklist[1].detail = "3 models (thin catalog — OC upstream issue)"
    assert hub_label_for_flow(flow, session) == "Setup OpenRouter (thin model catalog)"


def test_resolve_flow_id_from_alias_label():
    flow = get_flow("flow.model.openrouter")
    assert flow is not None
    session = _openrouter_session()
    session.checklist[0].done = True
    session.checklist[1].done = True
    label = hub_label_for_flow(flow, session)
    assert resolve_flow_id_from_hub_label(label, session) == "flow.model.openrouter"
    assert resolve_flow_id_from_hub_label("Setup OpenRouter", session) == "flow.model.openrouter"


def test_hub_next_hint_thin_catalog():
    session = _openrouter_session()
    session.checklist[1].done = False
    session.checklist[1].detail = "3 models (thin catalog — OC upstream issue)"
    hint = hub_next_hint(session)
    assert hint is not None
    assert "thin" in hint.lower() or "unreachable" in hint.lower()


def test_hub_labels_for_session_pairs():
    session = SessionState()
    pairs = hub_labels_for_session(session)
    assert len(pairs) == 1
    assert pairs[0][1] == "flow.model.openrouter"
