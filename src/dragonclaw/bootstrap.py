"""Workspace paths and minimal bootstrap helpers."""

from __future__ import annotations

from pathlib import Path


def default_workspace_dir() -> Path:
    return Path.home() / ".openclaw"


def ensure_workspace_dir(workspace_dir: Path) -> Path:
    workspace_dir = workspace_dir.expanduser().resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir
