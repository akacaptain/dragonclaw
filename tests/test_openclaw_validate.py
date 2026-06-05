import pytest
from pathlib import Path

from dragonclaw.openclaw_validate import (
    _parse_validate_output,
    resolve_openclaw_config_dir,
    resolve_openclaw_home,
)

pytestmark = pytest.mark.real_openclaw_validate


def test_resolve_openclaw_home_global_dot_openclaw(tmp_path, monkeypatch):
    user_home = tmp_path / "userhome"
    monkeypatch.setattr(Path, "home", lambda: user_home)
    oc_home = user_home / ".openclaw"
    oc_home.mkdir(parents=True)
    (oc_home / "openclaw.json").write_text("{}", encoding="utf-8")
    assert resolve_openclaw_home(oc_home) == user_home.resolve()
    assert resolve_openclaw_config_dir(user_home) == oc_home.resolve()


def test_resolve_openclaw_config_dir_prefers_dot_openclaw_over_home_json(tmp_path, monkeypatch):
    user_home = tmp_path / "userhome"
    monkeypatch.setattr(Path, "home", lambda: user_home)
    user_home.mkdir()
    (user_home / "openclaw.json").write_text("{}", encoding="utf-8")
    oc_home = user_home / ".openclaw"
    oc_home.mkdir()
    (oc_home / "openclaw.json").write_text('{"agents": {}}', encoding="utf-8")
    assert resolve_openclaw_config_dir(user_home) == oc_home.resolve()


def test_resolve_openclaw_home_project_nested_dot_openclaw(tmp_path):
    project = tmp_path / "myproject"
    oc_dir = project / ".openclaw"
    oc_dir.mkdir(parents=True)
    (oc_dir / "openclaw.json").write_text("{}", encoding="utf-8")
    assert resolve_openclaw_home(oc_dir) == project.resolve()


def test_parse_validate_json_issues():
    raw = """{
  "valid": false,
  "path": "/Users/captain/.openclaw/openclaw.json",
  "issues": [
    {
      "path": "<root>",
      "message": "Unrecognized key: \\"provider\\""
    }
  ]
}"""
    keys, ok = _parse_validate_output(raw)
    assert ok is False
    assert keys == ["provider"]
