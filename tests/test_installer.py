from pathlib import Path
from unittest.mock import patch

from dragonclaw.installer import (
    USER_NPM_PREFIX,
    build_install_plan,
    ensure_npm_prefix_on_path,
    execute_install,
    openclaw_binary_path,
    prerequisites_met,
    resolve_npm_install_prefix,
)


def test_build_install_plan_argv():
    with patch(
        "dragonclaw.installer.resolve_npm_install_prefix",
        return_value=(Path("/opt/homebrew"), False),
    ):
        plan = build_install_plan("2026.6.1")
    assert plan.install_argv == ["npm", "install", "-g", "openclaw@2026.6.1"]
    assert plan.user_local is False


def test_build_install_plan_user_local_argv():
    with patch(
        "dragonclaw.installer.resolve_npm_install_prefix",
        return_value=(USER_NPM_PREFIX, True),
    ):
        plan = build_install_plan("2026.6.1")
    assert plan.install_argv == [
        "npm",
        "install",
        "-g",
        "openclaw@2026.6.1",
        "--prefix",
        str(USER_NPM_PREFIX),
    ]
    assert plan.user_local is True


def test_execute_install_dry_run():
    with patch("dragonclaw.installer.prerequisites_met", return_value=(True, "ok")):
        result = execute_install(build_install_plan(), dry_run=True)
    assert result.ok is True
    assert result.dry_run is True
    assert "Dry run" in result.message


def test_resolve_npm_install_prefix_falls_back_when_global_not_writable():
    configured = Path("/opt/homebrew")
    with patch("dragonclaw.installer._npm_configured_prefix", return_value=configured):
        with patch("dragonclaw.installer._npm_install_target_writable", return_value=False):
            prefix, user_local = resolve_npm_install_prefix()
    assert prefix == USER_NPM_PREFIX
    assert user_local is True


def test_ensure_npm_prefix_on_path_prepends_bin(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=False):
        ensure_npm_prefix_on_path(tmp_path)
        path_parts = __import__("os").environ["PATH"].split(":")
        assert str(bin_dir) in path_parts
        assert path_parts[0] == str(bin_dir)


def test_execute_install_retries_on_eacces(monkeypatch, tmp_path: Path):
    calls: list[list[str]] = []
    binary = tmp_path / "openclaw"
    binary.write_text("#!/bin/sh\necho 2026.6.1\n")
    binary.chmod(0o755)

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        capture = kwargs.get("capture_output", True)

        class Proc:
            returncode = 243 if "--prefix" not in argv else 0
            stdout = ""
            stderr = (
                "npm error Error: EACCES: permission denied, mkdir '/opt/homebrew/lib/node_modules/openclaw'"
                if "--prefix" not in argv
                else ""
            )

        proc = Proc()
        if not capture:
            proc.stdout = None
            proc.stderr = None
        return proc

    monkeypatch.setattr("dragonclaw.installer.subprocess.run", fake_run)
    monkeypatch.setattr(
        "dragonclaw.installer.openclaw_binary_path",
        lambda npm_prefix=None: binary,
    )
    monkeypatch.setattr("dragonclaw.installer._run_capture", lambda argv, **kw: (0, "2026.6.1"))

    with patch(
        "dragonclaw.installer.resolve_npm_install_prefix",
        return_value=(Path("/opt/homebrew"), False),
    ):
        plan = build_install_plan("2026.6.1")
    with patch("dragonclaw.installer.prerequisites_met", return_value=(True, "ok")):
        result = execute_install(plan, dry_run=False, stream_output=False)
    assert result.ok is True
    assert result.user_local is True
    assert "verified" in result.message.lower()
    assert any("--prefix" in call for call in calls)


def test_openclaw_binary_path_finds_user_local(tmp_path: Path, monkeypatch):
    binary = tmp_path / "bin" / "openclaw"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr("dragonclaw.installer.USER_NPM_PREFIX", tmp_path)
    monkeypatch.setattr("dragonclaw.installer.shutil.which", lambda name: None)
    assert openclaw_binary_path() == binary
