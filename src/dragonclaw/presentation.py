"""Terminal presentation: menus, prompts, and confirmations."""

from __future__ import annotations

import re

import typer
from rich.console import Console

console = Console()

_SECRET_PROMPT_RE = re.compile(
    r"\b(token|api[_ -]?key|password|secret|credential)\b",
    re.IGNORECASE,
)


def render_welcome(
    *,
    version: str,
    oc_version: str | None = None,
    inference_mode: str = "local",
) -> None:
    console.print(f"[cyan]DragonClaw v{version}[/cyan] — OpenClaw setup assistant")
    if oc_version:
        console.print(f"[dim]Target OpenClaw pin: {oc_version}[/dim]")
    if inference_mode == "local":
        console.print(
            "[dim]Your config stays on this machine. The AI runs locally — no telemetry by default.[/dim]"
        )
        console.print(
            "[dim]First reply may take 30–90 seconds while the model loads (one-time download).[/dim]"
        )
    elif inference_mode.startswith("cloud"):
        console.print(
            "[dim]Your OpenClaw config stays on this machine. "
            "Setup questions are answered via OpenRouter (BYOK).[/dim]"
        )
    else:
        console.print("[dim]Your config stays on this machine.[/dim]")


def render_choice_menu(title: str, options: list[str]) -> None:
    console.print(f"\n[cyan]{title}[/cyan]")
    for index, label in enumerate(options, start=1):
        console.print(f"  {index}. {label}")
    console.print("  [dim](or describe in your own words)[/dim]")


def read_user_turn(*, secret: bool = False) -> str:
    """Read one user line. Secrets use the same visible prompt as OpenClaw."""
    _ = secret
    return typer.prompt("you").strip()


def last_message_suggests_secret(last_assistant: str | None) -> bool:
    if not last_assistant:
        return False
    return bool(_SECRET_PROMPT_RE.search(last_assistant))


def resolve_menu_choice(raw: str, options: list[str]) -> str:
    """Map a numeric choice to option label; pass through free text."""
    text = raw.strip()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(options):
            return options[index - 1]
    return text


def confirm_write(summary: str, *, default: bool = False) -> bool:
    console.print(f"\n[green]{summary}[/green]")
    return typer.confirm("OK?", default=default)


def render_mode_hint(mode: str) -> None:
    hints: dict[str, str] = {
        "onboarding": "Setup mode — I'll guide you through OpenClaw configuration.",
        "configure": "Configuration mode — tell me what you'd like to change.",
        "doctor": "Fix mode — describe what's wrong or ask me to fix your config.",
        "free": "Ask me anything about your OpenClaw setup.",
    }
    hint = hints.get(mode)
    if hint:
        console.print(f"[dim]{hint}[/dim]")
