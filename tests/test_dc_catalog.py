import json
from unittest.mock import patch

from dragonclaw.dc_catalog.openai_compatible import (
    OpenAICompatibleCatalogConfig,
    fetch_openai_compatible_catalog,
)
from dragonclaw.model_list import ModelCatalogEntry, catalog_for_provider


def test_fetch_openai_compatible_parses_data_array():
    payload = json.dumps(
        {
            "data": [
                {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4"},
                {"id": "openrouter/auto", "name": "Auto"},
            ]
        }
    )

    class FakeResponse:
        def read(self):
            return payload.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        entries, error = fetch_openai_compatible_catalog(
            OpenAICompatibleCatalogConfig(
                models_url="https://openrouter.ai/api/v1/models",
                provider_id="openrouter",
            ),
            api_key="sk-or-v1-test",
        )

    assert error is None
    assert len(entries) == 2
    ids = {entry.model_id for entry in entries}
    assert "openrouter/anthropic/claude-sonnet-4" in ids
    assert "openrouter/auto" in ids


def test_fetch_openai_compatible_401():
    import urllib.error

    def raise_http(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://openrouter.ai/api/v1/models",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    with patch("urllib.request.urlopen", side_effect=raise_http):
        entries, error = fetch_openai_compatible_catalog(
            OpenAICompatibleCatalogConfig(
                models_url="https://openrouter.ai/api/v1/models",
                provider_id="openrouter",
            ),
            api_key="bad",
        )

    assert entries == []
    assert error is not None
    assert "401" in error


def test_catalog_for_provider_prefers_dc_adapter(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dc_entries = [
        ModelCatalogEntry(model_id="openrouter/auto", display_name="Auto"),
    ]
    with patch(
        "dragonclaw.dc_catalog.fetch_dc_catalog",
        return_value=(dc_entries, "DragonClaw live catalog (1 models)"),
    ):
        entries, source = catalog_for_provider(workspace, "openrouter")
    assert len(entries) == 1
    assert "DragonClaw" in source
