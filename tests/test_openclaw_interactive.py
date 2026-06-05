from unittest.mock import patch

from dragonclaw.openclaw_interactive import InteractiveResult, run_openclaw_interactive


def test_interactive_missing_binary(tmp_path):
    with patch("dragonclaw.openclaw_interactive.openclaw_binary_path", return_value=None):
        result = run_openclaw_interactive(tmp_path, ["--help"])
    assert result.ok is False
    assert result.exit_code == 127


def test_interactive_foreground_success(tmp_path):
    class FakeProc:
        returncode = 0

    binary = tmp_path / "openclaw"
    binary.write_text("", encoding="utf-8")
    with patch("dragonclaw.openclaw_interactive.openclaw_binary_path", return_value=binary):
        with patch("subprocess.run", return_value=FakeProc()) as run_mock:
            result = run_openclaw_interactive(tmp_path, ["--help"])
    assert result.ok is True
    assert result.exit_code == 0
    run_mock.assert_called_once()
