"""Chat completion backend for the runtime planner."""

from __future__ import annotations

import os
from pathlib import Path

from dragonclaw.local_inference import LocalInferenceError, complete_chat as local_complete_chat


def complete_chat(
    messages: list[dict[str, str]],
    *,
    workspace_dir: Path | None = None,
    base_model: str | None = None,
) -> str:
    if _use_remote_completion(workspace_dir):
        from dragonclaw.llm_client import chat_completion, load_llm_config_for_workspace

        config = load_llm_config_for_workspace(workspace_dir)
        return chat_completion(messages, config=config)
    return local_complete_chat(messages, base_model=base_model)


def _use_remote_completion(workspace_dir: Path | None) -> bool:
    if os.environ.get("DRAGONCLAW_USE_REMOTE_API", "").strip().lower() in {"1", "true", "yes"}:
        return True
    from dragonclaw.inference_profile import should_use_remote_completion

    return should_use_remote_completion(workspace_dir)


__all__ = ["complete_chat", "LocalInferenceError"]
