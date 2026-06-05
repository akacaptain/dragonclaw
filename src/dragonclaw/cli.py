"""DragonClaw consumer CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from dragonclaw import __version__
from dragonclaw.bootstrap import default_workspace_dir, ensure_workspace_dir
from dragonclaw.chat_loop import run_chat_loop
from dragonclaw.inference_onboarding import inference_mode_label, run_inference_tier_menu
from dragonclaw.installer import build_install_plan, execute_install, format_prereq_report, openclaw_installed
from dragonclaw.openclaw_interactive import run_openclaw_interactive
from dragonclaw.openclaw_tools import run_doctor, tool_validate_config
from dragonclaw.presentation import UserExit, console, render_welcome

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _workspace(path: Path | None) -> Path:
    return ensure_workspace_dir(path or default_workspace_dir())


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    workspace: Annotated[
        Optional[Path],
        typer.Option("--workspace", help="OpenClaw workspace directory (~/.openclaw)"),
    ] = None,
) -> None:
    """DragonClaw — OpenClaw setup assistant."""
    if ctx.invoked_subcommand is not None:
        return

    ws = _workspace(workspace)
    try:
        profile = run_inference_tier_menu(ws)
        render_welcome(version=__version__, inference_mode=inference_mode_label(profile))

        if openclaw_installed():
            console.print("[green]OpenClaw is installed.[/green]")
        else:
            console.print(
                "[yellow]OpenClaw is not installed yet.[/yellow] Run: dragonclaw install --apply"
            )

        console.print(f"[bright_black]Workspace: {ws}[/bright_black]")
        run_chat_loop(ws)
    except UserExit:
        console.print("[bright_black]Goodbye.[/bright_black]")
        raise typer.Exit(0) from None


@app.command("validate")
def validate_cmd(
    workspace: Annotated[Optional[Path], typer.Option("--workspace")] = None,
) -> None:
    """Run openclaw config validate on the workspace."""
    ws = _workspace(workspace)
    report = tool_validate_config(ws)
    if report.ok:
        console.print("[green]Config validates OK.[/green]")
        raise typer.Exit(0)
    console.print("[red]Config validation failed.[/red]")
    if report.unrecognized_keys:
        console.print(f"Unrecognized keys: {', '.join(report.unrecognized_keys)}")
    if report.error:
        console.print(report.error)
    if report.raw_output:
        console.print(report.raw_output[:2000])
    raise typer.Exit(1)


@app.command("doctor")
def doctor_cmd(
    workspace: Annotated[Optional[Path], typer.Option("--workspace")] = None,
    fix: Annotated[bool, typer.Option("--fix", help="Pass --fix to openclaw doctor")] = False,
) -> None:
    """Run openclaw doctor (non-interactive) and print output."""
    ws = _workspace(workspace)
    result = run_doctor(ws, fix=fix, non_interactive=True)
    if result.output:
        console.print(result.output[:8000])
    if result.ok:
        raise typer.Exit(0)
    if result.error:
        console.print(f"[red]{result.error}[/red]")
    raise typer.Exit(result.exit_code or 1)


@app.command("install")
def install_cmd(
    version: Annotated[str, typer.Option("--version", help="OpenClaw npm version")] = "2026.6.1",
    apply: Annotated[bool, typer.Option("--apply", help="Run npm install (default is dry-run)")] = False,
) -> None:
    """Install or preview OpenClaw via npm."""
    console.print(format_prereq_report())
    plan = build_install_plan(version)
    console.print("\n".join(f"- {step}" for step in plan.steps))
    result = execute_install(plan, dry_run=not apply, stream_output=apply)
    if result.ok:
        console.print(f"[green]{result.message}[/green]")
        raise typer.Exit(0)
    console.print(f"[red]{result.message}[/red]")
    if result.output:
        console.print(result.output[:4000])
    raise typer.Exit(1)


@app.command("interactive")
def interactive_cmd(
    oc_args: Annotated[
        Optional[list[str]],
        typer.Argument(help="Arguments after -- passed to openclaw (e.g. -- --help)"),
    ] = None,
    workspace: Annotated[Optional[Path], typer.Option("--workspace")] = None,
    pty: Annotated[bool, typer.Option("--pty", help="Allocate PTY when stdin is not a TTY")] = False,
) -> None:
    """Foreground TTY handoff to openclaw (oc_interactive)."""
    ws = _workspace(workspace)
    argv = oc_args or ["--help"]
    result = run_openclaw_interactive(ws, argv, use_pty=pty)
    if not result.ok:
        if result.error:
            console.print(f"[red]{result.error}[/red]")
        raise typer.Exit(result.exit_code or 1)
