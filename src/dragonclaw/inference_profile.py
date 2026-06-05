"""Persist consumer inference mode (local base instruct vs remote BYOK)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from dragonclaw.bootstrap import default_workspace_dir
from dragonclaw.llm_client import (
    LLMConfig,
    LLMError,
    OPENROUTER_KEY_PREFIX,
    _normalize_api_key,
    probe_openrouter_auth,
    validate_openrouter_key_format,
)

# OpenRouter free tier — exact slug refined via smoke test as OC/OpenRouter catalogs change.
DEFAULT_REMOTE_MODEL = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
DEFAULT_REMOTE_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_SIGNUP_URL = "https://openrouter.ai/signup?ref=dragonclaw"
INFERENCE_PROFILE_FILENAME = "dragonclaw_inference.json"


class InferenceMode(str, Enum):
    LOCAL = "local"
    REMOTE_BYOK = "remote_byok"
    REMOTE_HOSTED = "remote_hosted"


@dataclass
class InferenceProfile:
    mode: InferenceMode = InferenceMode.LOCAL
    provider: str = "openrouter"
    model: str = DEFAULT_REMOTE_MODEL
    base_url: str = DEFAULT_REMOTE_BASE_URL
    api_key: str = ""
    install_id: str = ""
    defer_remote_setup: bool = False

    def is_remote(self) -> bool:
        return self.mode in {InferenceMode.REMOTE_BYOK, InferenceMode.REMOTE_HOSTED}

    def requires_api_key(self) -> bool:
        return self.mode == InferenceMode.REMOTE_BYOK

    def to_llm_config(self) -> LLMConfig:
        if not self.is_remote():
            raise LLMError("Inference profile is not in remote mode.")
        if self.mode == InferenceMode.REMOTE_HOSTED:
            raise LLMError("Hosted inference is not available yet.")
        key = _normalize_api_key(self.api_key)
        if len(key) < 8:
            raise LLMError(
                "No cloud API key configured. Run dragonclaw and choose "
                "'Use cloud assistant' to add your OpenRouter key."
            )
        validate_openrouter_key_format(key, base_url=self.base_url)
        return LLMConfig(api_key=key, base_url=self.base_url.rstrip("/"), model=self.model)


def inference_profile_path(workspace_dir: Path | None = None) -> Path:
    root = (workspace_dir or default_workspace_dir()).expanduser().resolve()
    return root / INFERENCE_PROFILE_FILENAME


def _ensure_install_id(data: dict[str, Any]) -> str:
    install_id = str(data.get("install_id", "")).strip()
    if install_id:
        return install_id
    return str(uuid.uuid4())


def load_inference_profile(workspace_dir: Path | None = None) -> InferenceProfile | None:
    path = inference_profile_path(workspace_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    mode_raw = str(raw.get("mode", InferenceMode.LOCAL.value))
    try:
        mode = InferenceMode(mode_raw)
    except ValueError:
        mode = InferenceMode.LOCAL
    return InferenceProfile(
        mode=mode,
        provider=str(raw.get("provider", "openrouter")),
        model=str(raw.get("model", DEFAULT_REMOTE_MODEL)),
        base_url=str(raw.get("base_url", DEFAULT_REMOTE_BASE_URL)),
        api_key=str(raw.get("api_key", "")),
        install_id=_ensure_install_id(raw),
        defer_remote_setup=bool(raw.get("defer_remote_setup", False)),
    )


def save_inference_profile(
    profile: InferenceProfile,
    workspace_dir: Path | None = None,
) -> Path:
    path = inference_profile_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not profile.install_id:
        profile.install_id = str(uuid.uuid4())
    payload = asdict(profile)
    payload["mode"] = profile.mode.value
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def resolve_inference_profile(workspace_dir: Path | None = None) -> InferenceProfile:
    loaded = load_inference_profile(workspace_dir)
    if loaded is not None:
        return loaded
    return InferenceProfile(install_id=str(uuid.uuid4()))


def should_preload_local_model(workspace_dir: Path | None = None) -> bool:
    import os

    if os.environ.get("DRAGONCLAW_USE_REMOTE_API", "").strip().lower() in {"1", "true", "yes"}:
        return False
    profile = load_inference_profile(workspace_dir)
    if profile is None:
        return True
    return not profile.is_remote()


def should_use_remote_completion(workspace_dir: Path | None = None) -> bool:
    import os

    if os.environ.get("DRAGONCLAW_USE_REMOTE_API", "").strip().lower() in {"1", "true", "yes"}:
        return True
    profile = load_inference_profile(workspace_dir)
    if profile is None:
        return False
    if profile.mode == InferenceMode.REMOTE_BYOK and profile.api_key.strip():
        return True
    if profile.mode == InferenceMode.REMOTE_HOSTED:
        return True
    return False


def verify_remote_profile(profile: InferenceProfile) -> str:
    cfg = profile.to_llm_config()
    return probe_openrouter_auth(config=cfg)


def set_local_mode(workspace_dir: Path | None = None) -> InferenceProfile:
    profile = resolve_inference_profile(workspace_dir)
    profile.mode = InferenceMode.LOCAL
    profile.defer_remote_setup = False
    save_inference_profile(profile, workspace_dir)
    return profile


def set_remote_byok_mode(
    api_key: str,
    *,
    workspace_dir: Path | None = None,
    model: str | None = None,
) -> InferenceProfile:
    profile = resolve_inference_profile(workspace_dir)
    profile.mode = InferenceMode.REMOTE_BYOK
    profile.api_key = _normalize_api_key(api_key)
    profile.defer_remote_setup = False
    if model:
        profile.model = model
    save_inference_profile(profile, workspace_dir)
    return profile


def defer_remote_setup(workspace_dir: Path | None = None) -> InferenceProfile:
    profile = resolve_inference_profile(workspace_dir)
    profile.defer_remote_setup = True
    save_inference_profile(profile, workspace_dir)
    return profile
