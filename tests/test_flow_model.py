from dragonclaw.flow_model import inspect_api_key, primary_satisfies_flow
from dragonclaw.flow_registry import build_model_provider_flow


def test_primary_satisfies_flow_provider_prefix():
    assert primary_satisfies_flow("openrouter", "openrouter/auto")
    assert not primary_satisfies_flow("openrouter", "anthropic/claude-opus-4-8")


def test_inspect_api_key_catches_capital_s():
    warning = inspect_api_key("openrouter", "Sk-or-v1-abc")
    assert warning is not None
    assert "capital S" in warning


def test_build_model_provider_flow_generic_steps():
    flow = build_model_provider_flow("openrouter", "Setup OpenRouter")
    assert flow.flow_id == "flow.model.openrouter"
    kinds = [step.kind for step in flow.steps]
    assert "oc_interactive" not in kinds
    assert kinds.count("dc_menu") == 2
    assert ("openrouter_auth", "OpenRouter API key configured") in flow.checklist
