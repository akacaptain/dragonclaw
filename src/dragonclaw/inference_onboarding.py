"""First-run inference tier selection and OpenRouter BYOK onboarding."""

from __future__ import annotations

from pathlib import Path

import typer

from dragonclaw.inference_capability import CapabilityReport, probe_local_capability
from dragonclaw.inference_profile import (
    OPENROUTER_SIGNUP_URL,
    InferenceMode,
    InferenceProfile,
    defer_remote_setup,
    load_inference_profile,
    resolve_inference_profile,
    save_inference_profile,
    set_local_mode,
    set_remote_byok_mode,
    verify_remote_profile,
)
from dragonclaw.llm_client import LLMError
from dragonclaw.presentation import (
    LOBSTER_ACCENT,
    LOBSTER_MUTED,
    console,
    run_dc_select,
    run_text_prompt,
)


def _prompt_openrouter_key() -> str:
    console.print(
        f"\n[bold {LOBSTER_ACCENT}]OpenRouter setup[/bold {LOBSTER_ACCENT}]\n"
        f"1. Create a free account: {OPENROUTER_SIGNUP_URL}\n"
        "2. Copy your API key (starts with sk-or-v1-).\n"
        "3. Paste it below — stored locally in ~/.openclaw/dragonclaw_inference.json\n"
        f"[{LOBSTER_MUTED}]Your key is only used for DragonClaw's setup assistant, "
        f"not sent elsewhere.[/{LOBSTER_MUTED}]"
    )
    while True:
        raw = run_text_prompt("Paste your OpenRouter API key (or type 'skip')")
        if not raw.strip():
            console.print("[yellow]Please paste your API key, or type 'skip' to decide later.[/yellow]")
            continue
        if raw.strip().lower() in {"skip", "later"}:
            return ""
        return raw.strip()


def run_inference_tier_menu(
    workspace_dir: Path,
    *,
    capability: CapabilityReport | None = None,
    force_prompt: bool = False,
) -> InferenceProfile:
    """Pick local vs remote inference; returns saved profile."""
    existing = load_inference_profile(workspace_dir)
    if existing is not None and existing.is_remote() and existing.api_key:
        return existing
    if existing is not None and existing.mode == InferenceMode.LOCAL and not force_prompt:
        if not existing.defer_remote_setup:
            return existing

    report = capability or probe_local_capability()
    profile = resolve_inference_profile(workspace_dir)

    if report.recommend_remote or force_prompt or (existing and existing.defer_remote_setup):
        if report.reasons:
            console.print("\n[yellow]This machine may struggle with local AI:[/yellow]")
            for reason in report.reasons:
                console.print(f"  • {reason}")

        options = [
            "Use cloud assistant (recommended on this machine)",
            "Continue with local AI anyway (may be slow)",
            "I'll add a key later",
        ]
        choice = run_dc_select("How should DragonClaw run its setup assistant?", options)

        if choice.startswith("Use cloud assistant"):
            key = _prompt_openrouter_key()
            if not key:
                defer_remote_setup(workspace_dir)
                console.print(
                    "[yellow]Continuing without a cloud key — local AI will be used when possible.[/yellow]"
                )
                if not report.recommend_remote:
                    return set_local_mode(workspace_dir)
                return profile

            try:
                candidate = set_remote_byok_mode(key, workspace_dir=workspace_dir)
                msg = verify_remote_profile(candidate)
                console.print(f"[green]{msg}[/green]")
                console.print(
                    "[dim]Cloud assistant active — prompts are sent to OpenRouter for setup help. "
                    "Your OpenClaw config files stay on this machine.[/dim]"
                )
                return candidate
            except LLMError as exc:
                console.print(f"[red]Could not verify key: {exc}[/red]")
                retry = typer.confirm("Try a different key?", default=True)
                if retry:
                    return run_inference_tier_menu(workspace_dir, capability=report, force_prompt=True)
                defer_remote_setup(workspace_dir)
                return set_local_mode(workspace_dir)

        if choice.startswith("I'll add a key later"):
            defer_remote_setup(workspace_dir)
            console.print(
                "[dim]Reminder: delete ~/.openclaw/dragonclaw_inference.json to re-run this menu.[/dim]"
            )
            return set_local_mode(workspace_dir)

        console.print(
            "[yellow]Local AI selected — first replies may take several minutes on CPU.[/yellow]"
        )
        return set_local_mode(workspace_dir)

    profile.mode = InferenceMode.LOCAL
    save_inference_profile(profile, workspace_dir)
    return profile


def inference_mode_label(profile: InferenceProfile | None) -> str:
    if profile is None or profile.mode == InferenceMode.LOCAL:
        return "local"
    if profile.mode == InferenceMode.REMOTE_BYOK:
        return f"cloud ({profile.provider}, {profile.model})"
    if profile.mode == InferenceMode.REMOTE_HOSTED:
        return "hosted (coming soon)"
    return "unknown"
