"""Interactive REPL for DragonClaw setup flows."""

from __future__ import annotations

from pathlib import Path

from dragonclaw.flow_engine import FlowEngine, begin_flow, refresh_hub_checklist
from dragonclaw.flow_registry import (
    get_flow,
    hub_labels_for_session,
    hub_next_hint,
    resolve_flow_id_from_hub_label,
)
from dragonclaw.flow_router import route_intent
from dragonclaw.openclaw_tools import run_doctor, tool_validate_config
from dragonclaw.presentation import (
    ASK_DRAGONCLAW_OPTION,
    LOBSTER_MUTED,
    QUIT_OPTION,
    UserExit,
    classify_global_menu_choice,
    console,
    format_checklist,
    run_dc_select,
    run_flow_pause_menu,
    run_text_prompt,
    with_global_menu_rows,
)
from dragonclaw.session_store import (
    load_session,
    prepare_session_startup,
    save_session,
)


def run_chat_loop(workspace_dir: Path) -> None:
    workspace_dir = workspace_dir.expanduser().resolve()
    session = prepare_session_startup(load_session(workspace_dir))
    save_session(workspace_dir, session)

    console.print(
        "\n[bright_black]Ctrl+C or type 'quit' at any prompt to exit.[/bright_black]"
    )

    try:
        while True:
            if not session.active_flow_id:
                refresh_hub_checklist(workspace_dir, session)

            if session.checklist:
                text = format_checklist(session.checklist)
                if text:
                    console.print(f"\n{text}")

            if session.active_flow_id:
                flow = get_flow(session.active_flow_id)
                if flow is None:
                    session.active_flow_id = None
                    session.flow_step_index = 0
                    save_session(workspace_dir, session)
                    continue
                engine = FlowEngine(workspace_dir, session)
                result = engine.run_flow(flow)
                if result.message:
                    console.print(result.message)
                if result.global_action == "back":
                    session.active_flow_id = None
                    session.flow_step_index = 0
                elif result.global_action == "ask":
                    _handle_ask_dragonclaw(
                        workspace_dir,
                        session,
                        result.message or "",
                    )
                elif result.completed and session.active_flow_id is None:
                    console.print(f"[green]{flow.label} finished.[/green]")
                elif not result.completed or result.failed:
                    pause_choice = run_flow_pause_menu()
                    pause_action = classify_global_menu_choice(pause_choice)
                    if pause_action == "back":
                        session.active_flow_id = None
                        session.flow_step_index = 0
                    elif pause_action == "ask":
                        _handle_ask_dragonclaw(workspace_dir, session)
                    elif pause_action == "quit" or pause_choice == QUIT_OPTION:
                        raise UserExit()
                save_session(workspace_dir, session)
                continue

            hint = hub_next_hint(session, workspace_dir=workspace_dir)
            if hint:
                console.print(f"\n[{LOBSTER_MUTED}]{hint}[/{LOBSTER_MUTED}]")

            hub_choice = _run_hub_select(session, workspace_dir)
            hub_action = classify_global_menu_choice(hub_choice)
            if hub_action == "quit":
                raise UserExit()
            if hub_action == "ask":
                _handle_ask_dragonclaw(workspace_dir, session)
                save_session(workspace_dir, session)
                continue

            flow_id = resolve_flow_id_from_hub_label(
                hub_choice, session, workspace_dir=workspace_dir
            )
            if flow_id is None:
                console.print("[yellow]That option is not available yet.[/yellow]")
                continue
            if flow_id.startswith("flow."):
                flow = get_flow(flow_id)
                if flow is None:
                    console.print(f"[red]Unknown flow: {flow_id}[/red]")
                    continue
                begin_flow(workspace_dir, session, flow)
                save_session(workspace_dir, session)
                continue

            console.print("[yellow]That setup flow is not available yet.[/yellow]")
    except UserExit:
        save_session(workspace_dir, session)
        console.print("[bright_black]Goodbye.[/bright_black]")


def _run_hub_select(session, workspace_dir: Path) -> str:
    content = [
        label for label, _ in hub_labels_for_session(session, workspace_dir=workspace_dir)
    ]
    labels = with_global_menu_rows(content, in_flow=False)
    return run_dc_select("What would you like to do?", labels)


def _handle_ask_dragonclaw(
    workspace_dir: Path,
    session,
    text: str | None = None,
) -> None:
    """Freeform path: separate text prompt routed to intent — not mixed into the menu."""
    if not text or not text.strip():
        text = run_text_prompt("Ask DragonClaw")
    if not text.strip():
        return
    flow_id = route_intent(text)
    if flow_id == "action.validate":
        _run_validate(workspace_dir)
        return
    if flow_id == "action.doctor":
        _run_doctor(workspace_dir)
        return
    if flow_id and flow_id.startswith("flow."):
        flow = get_flow(flow_id)
        if flow is not None:
            begin_flow(workspace_dir, session, flow)
            return
    console.print(
        "[yellow]I didn't match that to a setup flow yet. "
        "Try picking Setup OpenRouter from the menu, or describe setup openrouter.[/yellow]"
    )


def _run_validate(workspace_dir: Path) -> None:
    report = tool_validate_config(workspace_dir)
    if report.ok:
        console.print("[green]Config validates OK.[/green]")
    else:
        console.print("[red]Config validation failed.[/red]")
        if report.error:
            console.print(report.error[:500])


def _run_doctor(workspace_dir: Path) -> None:
    result = run_doctor(workspace_dir, non_interactive=True)
    if result.output:
        console.print(result.output[:4000])
    if not result.ok and result.error:
        console.print(f"[red]{result.error}[/red]")
