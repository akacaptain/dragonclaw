import os
from unittest.mock import patch

import pytest

from dragonclaw.presentation import (
    ASK_DRAGONCLAW_OPTION,
    FLOW_PAUSE_HUB,
    FREE_TEXT_OPTION,
    LOBSTER_ACCENT,
    QUIT_OPTION,
    UserExit,
    _menu_style,
    classify_global_menu_choice,
    format_checklist,
    is_exit_command,
    menus_use_tty,
    resolve_menu_choice,
    run_dc_select,
    run_select_menu,
    run_text_prompt,
    with_global_menu_rows,
)
from dragonclaw.session_store import ChecklistItem


def test_menus_use_tty_respects_plain_ui(monkeypatch):
    monkeypatch.setenv("DRAGONCLAW_PLAIN_UI", "1")
    assert menus_use_tty() is False


def test_resolve_menu_choice_plain_fallback():
    options = ["Setup OpenRouter", "Validate config"]
    assert resolve_menu_choice("1", options) == "Setup OpenRouter"
    assert resolve_menu_choice("setup openrouter", options) == "setup openrouter"


def test_free_text_option_constant():
    assert "describe" in FREE_TEXT_OPTION.lower()


def test_is_exit_command():
    assert is_exit_command("quit")
    assert is_exit_command("EXIT")
    assert is_exit_command("q")
    assert not is_exit_command("setup openrouter")


def test_run_select_menu_none_raises_user_exit(monkeypatch):
    monkeypatch.setenv("DRAGONCLAW_PLAIN_UI", "1")

    with patch("dragonclaw.presentation.typer.prompt", return_value=""):
        with pytest.raises(UserExit):
            run_select_menu("Pick one", ["A", "B"])


def test_run_text_prompt_quit_raises_user_exit(monkeypatch):
    monkeypatch.setenv("DRAGONCLAW_PLAIN_UI", "1")

    with patch("dragonclaw.presentation.typer.prompt", return_value="quit"):
        with pytest.raises(UserExit):
            run_text_prompt("Enter value")


def test_run_select_menu_plain_numeric_choice(monkeypatch):
    monkeypatch.setenv("DRAGONCLAW_PLAIN_UI", "1")

    with patch("dragonclaw.presentation.typer.prompt", return_value="1"):
        assert run_select_menu("Pick one", ["Alpha", "Beta"]) == "Alpha"


def test_run_dc_select_plain_numeric_choice(monkeypatch):
    monkeypatch.setenv("DRAGONCLAW_PLAIN_UI", "1")

    with patch("dragonclaw.presentation.typer.prompt", return_value="2"):
        assert run_dc_select("Pick one", ["Alpha", "Beta"]) == "Beta"


def test_run_dc_select_requires_options():
    with pytest.raises(ValueError):
        run_dc_select("Empty", [])


def test_quit_option_constant():
    assert QUIT_OPTION == "Quit"


def test_ask_dragonclaw_option_constant():
    assert ASK_DRAGONCLAW_OPTION == "Ask DragonClaw"


def test_with_global_menu_rows_hub():
    rows = with_global_menu_rows(["Setup OpenRouter"], in_flow=False)
    assert rows == ["Setup OpenRouter", ASK_DRAGONCLAW_OPTION, QUIT_OPTION]
    assert FLOW_PAUSE_HUB not in rows


def test_with_global_menu_rows_in_flow():
    rows = with_global_menu_rows(["Model A"], in_flow=True)
    assert rows[-3:] == [ASK_DRAGONCLAW_OPTION, FLOW_PAUSE_HUB, QUIT_OPTION]


def test_classify_global_menu_choice():
    assert classify_global_menu_choice(ASK_DRAGONCLAW_OPTION) == "ask"
    assert classify_global_menu_choice(FLOW_PAUSE_HUB) == "back"
    assert classify_global_menu_choice(QUIT_OPTION) == "quit"
    assert classify_global_menu_choice("Setup OpenRouter") is None


def test_no_dual_highlight_style():
    style = _menu_style()
    rules = {frozenset(names): attrs for names, attrs in style.class_names_and_attrs}
    selected = rules[frozenset({"selected"})]
    assert selected.color is None and selected.bgcolor is None
    qmark = rules[frozenset({"qmark"})]
    assert qmark.color is None and qmark.bgcolor is None
    question = rules[frozenset({"question"})]
    assert question.color.upper().lstrip("#") == LOBSTER_ACCENT.lstrip("#").upper()
    assert question.bold is True
    highlighted = rules[frozenset({"highlighted"})]
    assert highlighted.bgcolor is None


def test_select_menu_tty_does_not_pass_default(monkeypatch):
    monkeypatch.delenv("DRAGONCLAW_PLAIN_UI", raising=False)

    with (
        patch("dragonclaw.presentation.menus_use_tty", return_value=True),
        patch("dragonclaw.presentation.console.print"),
        patch("questionary.select") as mock_select,
    ):
        mock_select.return_value.unsafe_ask.return_value = "Alpha"
        assert run_select_menu("Pick one", ["Alpha", "Beta"]) == "Alpha"

    assert "default" not in mock_select.call_args.kwargs
    assert mock_select.call_args.args[0] == " "


def test_format_checklist_uses_lobster_palette():
    text = format_checklist(
        [
            ChecklistItem(id="auth", label="Auth", done=True, detail="ok"),
            ChecklistItem(id="primary", label="Primary", done=False),
        ]
    )
    assert LOBSTER_ACCENT in text
    assert "Auth" in text
    assert "Primary" in text
