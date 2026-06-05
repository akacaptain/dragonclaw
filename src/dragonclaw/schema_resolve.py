"""Resolve schema.json and artifacts directory for runtime."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_schema_path(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    env_path = os.environ.get("DRAGONCLAW_SCHEMA_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(Path("artifacts/schema.json").expanduser())
    project_root = Path(__file__).resolve().parents[2]
    candidates.append(project_root / "artifacts" / "schema.json")
    package_artifacts = Path(__file__).resolve().parent / "artifacts"
    candidates.append(package_artifacts / "schema.json")
    for path in candidates:
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def resolve_artifacts_dir(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    candidates.append(Path("artifacts").expanduser())
    project_root = Path(__file__).resolve().parents[2]
    candidates.append(project_root / "artifacts")
    package_artifacts = Path(__file__).resolve().parent / "artifacts"
    candidates.append(package_artifacts)
    for path in candidates:
        if path.exists() and path.is_dir():
            return path.resolve()
    return None
