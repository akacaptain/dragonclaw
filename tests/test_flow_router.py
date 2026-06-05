from dragonclaw.flow_router import hub_menu_labels, hub_menu_options, route_intent


def test_hub_options_only_registered_flows():
    labels = hub_menu_labels()
    flow_ids = [fid for _, fid in hub_menu_options()]
    assert "Validate config" not in labels
    assert "Run openclaw doctor" not in labels
    assert all(fid and fid.startswith("flow.") for fid in flow_ids)
    assert any("openrouter" in fid.lower() for fid in flow_ids)


def test_route_setup_openrouter():
    assert route_intent("setup openrouter") == "flow.model.openrouter"
    assert route_intent("Setup OpenRouter please") == "flow.model.openrouter"


def test_route_unknown():
    assert route_intent("fix my gateway") is None
