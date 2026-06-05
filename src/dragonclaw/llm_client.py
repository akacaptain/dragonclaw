"""OpenAI-compatible chat client for DragonClaw runtime."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str


class LLMError(RuntimeError):
    pass


OPENROUTER_KEY_PREFIX = "sk-or-v1-"


def _normalize_api_key(raw: str | None) -> str:
    if not raw:
        return ""
    key = raw.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        key = key[1:-1].strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key


def validate_openrouter_key_format(api_key: str, *, base_url: str) -> None:
    """Local format check — catches common paste typos before a misleading 401."""
    if "openrouter.ai" not in base_url:
        return
    if api_key.startswith(OPENROUTER_KEY_PREFIX):
        return
    if api_key.lower().startswith(OPENROUTER_KEY_PREFIX):
        raise LLMError(
            "OpenRouter API key prefix casing is wrong: keys must start with exactly "
            f"{OPENROUTER_KEY_PREFIX!r} (lowercase sk). "
            f"Yours starts with {api_key[:12]!r}. "
            "A capital S in Sk-or-v1- is a common typo; OpenRouter often returns "
            "HTTP 401 Missing Authentication header for this."
        )
    raise LLMError(
        f"OpenRouter API key should start with {OPENROUTER_KEY_PREFIX!r}; "
        f"yours starts with {api_key[:16]!r}."
    )


def load_llm_config() -> LLMConfig:
    return load_llm_config_for_workspace(None)


def load_llm_config_for_workspace(workspace_dir: Path | None) -> LLMConfig:
    from dragonclaw.inference_profile import InferenceMode, load_inference_profile

    profile = load_inference_profile(workspace_dir)
    if profile is not None and profile.mode == InferenceMode.REMOTE_BYOK and profile.api_key.strip():
        return profile.to_llm_config()

    api_key = _normalize_api_key(
        os.environ.get("DRAGONCLAW_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if len(api_key) < 8:
        raise LLMError(
            "No API key found. Set DRAGONCLAW_API_KEY (or OPENAI_API_KEY) in this shell, e.g.\n"
            '  export DRAGONCLAW_API_KEY="sk-or-v1-..."\n'
            "OpenRouter keys usually start with sk-or-v1-.\n"
            "Or run dragonclaw and choose 'Use cloud assistant' to store a key locally."
        )
    base_url = (
        os.environ.get("DRAGONCLAW_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://openrouter.ai/api/v1"
    ).rstrip("/")
    model = os.environ.get("DRAGONCLAW_MODEL") or os.environ.get("OPENAI_MODEL") or "openai/gpt-4o-mini"
    validate_openrouter_key_format(api_key, base_url=base_url)
    return LLMConfig(api_key=api_key, base_url=base_url, model=model)


def chat_completion(
    messages: list[dict[str, str]],
    *,
    config: LLMConfig | None = None,
    temperature: float = 0.2,
    timeout_s: float = 120.0,
    json_object: bool = True,
) -> str:
    cfg = config or load_llm_config()
    url = f"{cfg.base_url}/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in cfg.base_url:
        headers["HTTP-Referer"] = os.environ.get(
            "DRAGONCLAW_OPENROUTER_REFERER", "https://github.com/akacaptain/dragonclaw"
        )
        headers["X-Title"] = os.environ.get("DRAGONCLAW_OPENROUTER_TITLE", "DragonClaw")
    request = Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_s) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if (
            exc.code == 401
            and "Missing Authentication" in detail
            and "openrouter.ai" in cfg.base_url
            and cfg.api_key.lower().startswith(OPENROUTER_KEY_PREFIX)
            and not cfg.api_key.startswith(OPENROUTER_KEY_PREFIX)
        ):
            hint = (
                " Hint: OpenRouter key prefix casing looks wrong "
                f"(use {OPENROUTER_KEY_PREFIX!r}, not {cfg.api_key[:12]!r})."
            )
        raise LLMError(f"LLM HTTP {exc.code}: {detail}{hint}") from exc
    except URLError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    choices = raw.get("choices")
    if not choices:
        raise LLMError(f"LLM returned no choices: {raw}")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMError(f"LLM returned empty content: {raw}")
    return content.strip()


def mask_api_key(api_key: str) -> str:
    key = _normalize_api_key(api_key)
    if len(key) <= 12:
        return "(too short)"
    return f"{key[:10]}...{key[-4]} (len {len(key)})"


def probe_openrouter_auth(*, config: LLMConfig | None = None) -> str:
    """One minimal chat request to verify Authorization reaches OpenRouter."""
    cfg = config or load_llm_config()
    chat_completion(
        [{"role": "user", "content": "Reply with JSON: {\"ok\": true}"}],
        config=cfg,
        temperature=0,
        json_object=True,
    )
    return f"OK — authenticated to {cfg.base_url} as model {cfg.model}"
