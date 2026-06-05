"""Terminal presentation: menus, prompts, and confirmations."""

from __future__ import annotations

import os
import re
import sys

import typer
from rich.console import Console

console = Console()

_SECRET_PROMPT_RE = re.compile(
    r"\b(token|api[_ -]?key|password|secret|credential)\b",
    re.IGNORECASE,
)

FREE_TEXT_OPTION = "(describe in your own words)"
ASK_DRAGONCLAW_OPTION = "Ask DragonClaw"
ENTER_MODEL_ID_MANUALLY = "Enter model id manually"
FLOW_PAUSE_RETRY = "Retry this step"
FLOW_PAUSE_HUB = "Back to hub"
QUIT_OPTION = "Quit"

EXIT_COMMANDS = frozenset({"quit", "exit", "q"})

_MENU_STYLE = None


class UserExit(Exception):
    """User requested exit (Ctrl+C or quit command)."""


def is_exit_command(text: str) -> bool:
    return text.strip().lower() in EXIT_COMMANDS


def _raise_on_exit(text: str | None) -> str:
    if text is None or is_exit_command(text):
        raise UserExit()
    return text


def _menu_style():
    global _MENU_STYLE
    if _MENU_STYLE is None:
        from questionary import Style

        _MENU_STYLE = Style(
            [
                ("qmark", "fg:ansicyan bold"),
                ("question", "fg:ansicyan bold"),
                ("answer", "fg:ansigreen bold"),
                ("pointer", "fg:ansicyan bold"),
                ("highlighted", "fg:ansiwhite bg:ansicyan bold"),
                # Neutralize default-row styling — only highlighted row shows active state.
                ("selected", ""),
                ("instruction", "fg:ansibrightblack"),
            ]
        )
    return _MENU_STYLE


def menus_use_tty() -> bool:
    """True when scrollable OC-style menus are available."""
    if os.environ.get("DRAGONCLAW_PLAIN_UI", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return sys.stdin.isatty()


def render_welcome(
    *,
    version: str,
    oc_version: str | None = None,
    inference_mode: str = "local",
) -> None:
    console.print(f"[bold blue]DragonClaw v{version}[/bold blue] — OpenClaw setup assistant")
    if oc_version:
        console.print(f"[bright_black]Target OpenClaw pin: {oc_version}[/bright_black]")
    if inference_mode == "local":
        console.print(
            "[bright_black]Your config stays on this machine. "
            "The AI runs locally — no telemetry by default.[/bright_black]"
        )
        console.print(
            "[bright_black]First reply may take 30–90 seconds while the model loads "
            "(one-time download).[/bright_black]"
        )
    elif inference_mode.startswith("cloud"):
        console.print(
            "[bright_black]Your OpenClaw config stays on this machine. "
            "Setup questions are answered via OpenRouter (BYOK).[/bright_black]"
        )
    else:
        console.print("[bright_black]Your config stays on this machine.[/bright_black]")


def render_choice_menu(title: str, options: list[str]) -> None:
    """Static numbered menu — plain-UI fallback."""
    console.print(f"\n[bold blue]{title}[/bold blue]")
    for index, label in enumerate(options, start=1):
        console.print(f"  {index}. {label}")
    console.print(f"  [bright_black]{FREE_TEXT_OPTION}[/bright_black]")


def run_autocomplete_prompt(
    title: str,
    options: list[str],
    *,
    instruction: str = "(Type to search or enter your own text)",
) -> str:
    """Type-first prompt with suggestions. Raises UserExit on Ctrl+C or quit."""
    choices = list(options)

    if menus_use_tty():
        import questionary

        try:
            message = f"{title} {instruction}" if instruction else title
            value = questionary.autocomplete(
                message,
                choices=choices,
                style=_menu_style(),
                match_middle=True,
                ignore_case=True,
            ).unsafe_ask()
        except KeyboardInterrupt:
            raise UserExit() from None
        return _raise_on_exit(value if value is None else str(value).strip())

    render_choice_menu(title, options)
    console.print(f"  [bright_black]{len(options) + 1}. {QUIT_OPTION}[/bright_black]")
    try:
        raw = typer.prompt("you").strip()
    except (KeyboardInterrupt, EOFError):
        raise UserExit() from None
    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(options):
            return _raise_on_exit(options[index - 1])
        if index == len(options) + 1:
            raise UserExit()
    return _raise_on_exit(raw)


def run_hub_prompt(title: str, options: list[str]) -> str:
    """Hub input: type-first with menu suggestions and Quit."""
    hub_options = list(options) + [QUIT_OPTION]
    value = run_autocomplete_prompt(
        title,
        hub_options,
        instruction="(Type to search or describe what you want)",
    )
    if value == QUIT_OPTION:
        raise UserExit()
    return value


def with_global_menu_rows(choices: list[str], *, in_flow: bool) -> list[str]:
    """Append Ask / Back (in-flow) / Quit to any content menu."""
    rows = list(choices)
    rows.append(ASK_DRAGONCLAW_OPTION)
    if in_flow:
        rows.append(FLOW_PAUSE_HUB)
    rows.append(QUIT_OPTION)
    return rows


def classify_global_menu_choice(choice: str) -> str | None:
    """Return ask|back|quit when choice is global chrome; else None."""
    if choice == ASK_DRAGONCLAW_OPTION:
        return "ask"
    if choice == FLOW_PAUSE_HUB:
        return "back"
    if choice == QUIT_OPTION:
        return "quit"
    return None


def run_oc_style_select(
    title: str,
    options: list[str],
    *,
    initial_index: int = 0,
) -> str:
    """OC-style select: single moving highlight, type-to-filter, no static default bar."""
    if not options:
        raise ValueError("run_oc_style_select requires at least one option")
    clamped = initial_index if 0 <= initial_index < len(options) else 0
    return run_select_menu(
        title,
        options,
        default_index=clamped,
        use_search_filter=True,
        pointer="›",
    )


def run_dc_select(
    title: str,
    options: list[str],
    *,
    default: str | None = None,
    initial_index: int | None = None,
) -> str:
    """DC standard menu: scrollable list, type filters rows only, one Enter confirms a row."""
    if not options:
        raise ValueError("run_dc_select requires at least one option")
    index = 0
    if initial_index is not None:
        index = initial_index
    elif default is not None:
        for idx, option in enumerate(options):
            if option == default:
                index = idx
                break
    return run_oc_style_select(title, options, initial_index=index)


def run_flow_pause_menu() -> str:
    """When a flow step is cancelled or failed — stay in flow unless user picks Back to hub."""
    return run_dc_select(
        "Setup paused — what next?",
        [FLOW_PAUSE_RETRY, FLOW_PAUSE_HUB, QUIT_OPTION],
        default=FLOW_PAUSE_RETRY,
    )


def run_select_menu(
    title: str,
    options: list[str],
    *,
    include_free_text: bool = False,
    default_index: int = 0,
    use_search_filter: bool = False,
    pointer: str = "›",
) -> str:
    """Scrollable select (arrow keys + Enter). Raises UserExit on Ctrl+C or quit."""
    choices = list(options)
    if include_free_text:
        choices.append(FREE_TEXT_OPTION)

    if menus_use_tty():
        import questionary

        default = choices[default_index] if 0 <= default_index < len(choices) else None
        instruction = "(Type to filter, or use arrow keys)" if use_search_filter else "(Use arrow keys)"
        try:
            value = questionary.select(
                title,
                choices=choices,
                default=default,
                pointer=pointer,
                instruction=instruction,
                style=_menu_style(),
                use_arrow_keys=True,
                use_jk_keys=not use_search_filter,
                use_emacs_keys=True,
                use_search_filter=use_search_filter,
                show_selected=False,
            ).unsafe_ask()
        except KeyboardInterrupt:
            raise UserExit() from None
        return _raise_on_exit(value if value is None else str(value).strip())

    if include_free_text:
        console.print(f"\n[bold blue]{title}[/bold blue]")
        for index, label in enumerate(choices, start=1):
            console.print(f"  {index}. {label}")
    else:
        render_choice_menu(title, options)
    try:
        raw = typer.prompt("you").strip()
    except (KeyboardInterrupt, EOFError):
        raise UserExit() from None
    if not raw:
        raise UserExit()
    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(choices):
            return _raise_on_exit(choices[index - 1])
    return _raise_on_exit(raw)


def run_text_prompt(message: str, *, secret: bool = False) -> str:
    """Single-line text or password prompt. Raises UserExit on Ctrl+C or quit."""
    if menus_use_tty():
        import questionary

        try:
            if secret:
                value = questionary.password(
                    message,
                    style=_menu_style(),
                ).unsafe_ask()
            else:
                value = questionary.text(
                    message,
                    style=_menu_style(),
                ).unsafe_ask()
        except KeyboardInterrupt:
            raise UserExit() from None
        if value is None:
            raise UserExit()
        return _raise_on_exit(str(value).strip())

    console.print(f"\n[bold blue]{message}[/bold blue]")
    try:
        raw = typer.prompt("you", hide_input=secret).strip()
    except (KeyboardInterrupt, EOFError):
        raise UserExit() from None
    return _raise_on_exit(raw)


def read_user_turn(*, secret: bool = False) -> str:
    """Read one user line. Prefer run_text_prompt for flow steps."""
    return run_text_prompt("you", secret=secret)


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
        console.print(f"[bright_black]{hint}[/bright_black]")
