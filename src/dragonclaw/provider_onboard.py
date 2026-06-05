"""OC plugin-aligned provider auth + default model setup for DragonClaw onboarding."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dragonclaw.openclaw_tools import _run_openclaw_cli


@dataclass(frozen=True)
class ProviderAuthChoice:
    choice_id: str
    method: str
    cli_flag: str | None
    option_key: str | None
    label: str
    env_var: str | None = None

    def accepts_api_key(self) -> bool:
        if self.method == "api-key":
            return bool(self.cli_flag)
        return self.method == "env-var" and bool(self.env_var)


@dataclass(frozen=True)
class ProviderOnboardSpec:
    provider_id: str
    label: str
    default_model_ref: str | None
    auth_choices: tuple[ProviderAuthChoice, ...]

    def preferred_setup_choice(self) -> ProviderAuthChoice | None:
        for method in ("api-key", "env-var", "local"):
            for choice in self.auth_choices:
                if choice.method == method:
                    return choice
        return self.auth_choices[0] if self.auth_choices else None

    def requires_api_key(self) -> bool:
        choice = self.preferred_setup_choice()
        return choice is not None and choice.accepts_api_key()

    def supports_automated_setup(self) -> bool:
        choice = self.preferred_setup_choice()
        if choice is None:
            return False
        return choice.method in {"api-key", "env-var", "local"}


def _load_provider_catalog() -> dict[str, Any]:
    from dragonclaw.provider_catalog import load_provider_catalog_document

    payload = load_provider_catalog_document()
    return payload if isinstance(payload, dict) else {}


def load_provider_onboard_spec(provider_id: str) -> ProviderOnboardSpec | None:
    provider_id = provider_id.strip().lower()
    payload = _load_provider_catalog()
    for raw in payload.get("providers") or []:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("id", "")).lower() != provider_id:
            continue
        choices: list[ProviderAuthChoice] = []
        for item in raw.get("auth_choices") or []:
            if not isinstance(item, dict):
                continue
            choices.append(
                ProviderAuthChoice(
                    choice_id=str(item.get("choice_id", "")),
                    method=str(item.get("method", "")),
                    cli_flag=item.get("cli_flag"),
                    option_key=item.get("option_key"),
                    label=str(item.get("label") or item.get("choice_id", "")),
                    env_var=item.get("env_var"),
                )
            )
        return ProviderOnboardSpec(
            provider_id=provider_id,
            label=str(raw.get("label") or provider_id.replace("-", " ").title()),
            default_model_ref=raw.get("default_model_ref"),
            auth_choices=tuple(choices),
        )
    return None


def _auth_profile_paths(workspace_dir: Path) -> list[Path]:
    workspace_dir = workspace_dir.expanduser().resolve()
    paths = [
        workspace_dir / "auth-profiles.json",
        workspace_dir / "agents" / "main" / "agent" / "auth-profiles.json",
    ]
    paths.extend(sorted(workspace_dir.glob("**/auth-profiles.json")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _read_openclaw_config(workspace_dir: Path) -> dict[str, Any]:
    path = workspace_dir.expanduser().resolve() / "openclaw.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _env_var_has_value(config: dict[str, Any], env_var: str) -> bool:
    env = config.get("env")
    if not isinstance(env, dict):
        return False
    vars_block = env.get("vars")
    if isinstance(vars_block, dict):
        value = vars_block.get(env_var)
        if value is not None and str(value).strip():
            return True
    value = env.get(env_var)
    return value is not None and str(value).strip() != ""


def workspace_has_provider_auth(workspace_dir: Path, provider_id: str) -> bool:
    provider_id = provider_id.strip().lower()
    spec = load_provider_onboard_spec(provider_id)
    if spec:
        config = _read_openclaw_config(workspace_dir)
        for choice in getattr(spec, "auth_choices", ()):
            if choice.method == "env-var" and choice.env_var:
                if _env_var_has_value(config, choice.env_var):
                    return True
    for path in _auth_profile_paths(workspace_dir):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        if not isinstance(profiles, dict):
            continue
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            if str(profile.get("provider", "")).lower() == provider_id:
                return True
    return False


def _apply_env_var_auth(
    workspace_dir: Path,
    spec: ProviderOnboardSpec,
    choice: ProviderAuthChoice,
    api_key: str,
    *,
    create_backups: bool = True,
) -> None:
    from dragonclaw.config_apply import apply_config_plan
    from dragonclaw.config_repair import validate_merged_openclaw

    env_var = (choice.env_var or "").strip()
    if not env_var:
        raise ValueError(f"Provider {spec.provider_id} is missing an env var for API key auth")

    plan: dict[str, Any] = {
        "openclaw.json": {
            "env": {
                "vars": {
                    env_var: api_key,
                }
            }
        }
    }
    if spec.default_model_ref:
        plan["openclaw.json"]["agents"] = {
            "defaults": {
                "model": {"primary": spec.default_model_ref},
            }
        }
    ok, err = validate_merged_openclaw(workspace_dir, plan)
    if not ok:
        raise ValueError(err or f"{env_var} failed validation")
    apply_config_plan(workspace_dir, plan, create_backups=create_backups)


def run_provider_onboard_setup(
    workspace_dir: Path,
    spec: ProviderOnboardSpec,
    *,
    api_key: str | None = None,
    timeout_s: float = 120.0,
) -> str:
    """Run `openclaw onboard --non-interactive` for one provider (auth + default primary)."""
    choice = spec.preferred_setup_choice()
    if choice is None:
        raise ValueError(f"No onboard auth choice for {spec.provider_id}")

    argv = [
        "onboard",
        "--non-interactive",
        "--accept-risk",
        "--auth-choice",
        choice.choice_id,
        "--skip-channels",
        "--skip-skills",
        "--skip-search",
        "--skip-health",
    ]
    if choice.method == "env-var":
        key = (api_key or "").strip()
        if not key:
            raise ValueError("API key is required")
        _apply_env_var_auth(workspace_dir, spec, choice, key)
        return f"{spec.label} API key saved to env.vars.{choice.env_var}."
    if choice.method == "api-key":
        if not choice.cli_flag:
            raise ValueError(f"Provider {spec.provider_id} is missing a CLI flag for API key auth")
        key = (api_key or "").strip()
        if not key:
            raise ValueError("API key is required")
        flag = choice.cli_flag.strip()
        if not flag.startswith("--"):
            flag = f"--{flag}"
        argv.extend([flag, key])
    elif choice.method != "local":
        raise ValueError(
            f"Provider {spec.provider_id} requires {choice.method} auth — "
            "use openclaw configure for Model or pick an API-key provider."
        )

    result = _run_openclaw_cli(workspace_dir, argv, timeout_s=timeout_s)
    if not result.ok:
        detail = result.error or result.output or "openclaw onboard failed"
        raise ValueError(detail.strip())
    return _format_onboard_success_message(spec)


def _format_onboard_success_message(spec: ProviderOnboardSpec) -> str:
    """Consumer-facing summary — never pass through raw openclaw onboard stdout (tips, configure hints)."""
    parts = [f"{spec.label} connected."]
    if spec.default_model_ref:
        parts.append(
            f"Default router model is {spec.default_model_ref} — choose your preferred model next."
        )
    return " ".join(parts)


def apply_model_primary(
    workspace_dir: Path,
    model_ref: str,
    *,
    create_backups: bool = True,
) -> None:
    from dragonclaw.config_apply import apply_config_plan
    from dragonclaw.config_repair import validate_merged_openclaw

    workspace_dir = workspace_dir.expanduser().resolve()
    plan = {
        "openclaw.json": {
            "agents": {
                "defaults": {
                    "model": {"primary": model_ref},
                }
            }
        }
    }
    ok, err = validate_merged_openclaw(workspace_dir, plan)
    if not ok:
        raise ValueError(err or f"model.primary={model_ref} failed validation")
    apply_config_plan(workspace_dir, plan, create_backups=create_backups)
