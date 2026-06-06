"""Live model catalog via OpenAI-compatible GET /models endpoints."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from dragonclaw.model_list import ModelCatalogEntry, normalize_model_key


@dataclass(frozen=True)
class OpenAICompatibleCatalogConfig:
    models_url: str
    provider_id: str
    timeout_s: float = 30.0


def fetch_openai_compatible_catalog(
    config: OpenAICompatibleCatalogConfig,
    *,
    api_key: str | None = None,
) -> tuple[list[ModelCatalogEntry], str | None]:
    """Return (entries, error). error is set when request failed; entries may still be empty."""
    provider = config.provider_id.strip().lower()
    headers = {"Accept": "application/json", "User-Agent": "DragonClaw/1.0"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    request = urllib.request.Request(config.models_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_s) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except OSError:
            pass
        if exc.code in {401, 403}:
            return [], (
                f"Provider rejected the API key (HTTP {exc.code}). "
                "Check the key is valid and uses the correct prefix."
            )
        return [], f"Models API failed: HTTP {exc.code}" + (f" — {body}" if body else "")
    except urllib.error.URLError as exc:
        return [], f"Could not reach models API: {exc.reason}"
    except TimeoutError:
        return [], "Models API timed out."

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [], "Models API returned invalid JSON."

    models = _extract_model_rows(payload)
    entries: list[ModelCatalogEntry] = []
    seen: set[str] = set()
    for row in models:
        model_id = normalize_model_key(str(row.get("id") or ""), provider)
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        name = str(row.get("name") or row.get("id") or model_id).strip()
        entries.append(ModelCatalogEntry(model_id=model_id, display_name=name))

    entries.sort(key=lambda item: (item.display_name.lower(), item.model_id.lower()))
    return entries, None


def _extract_model_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        models = payload.get("models")
        if isinstance(models, list):
            return [item for item in models if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []
