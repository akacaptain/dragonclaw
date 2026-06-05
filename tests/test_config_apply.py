import json

from dragonclaw.config_apply import apply_config_plan


def test_apply_config_plan_writes_multiple_json_files(tmp_path):
    workspace = tmp_path / "workspace"
    plan = {
        "openclaw.json": {"provider": "openai", "tools": {"elevated": {"enabled": True}}},
        "auth/profiles/default.json": {"name": "default", "token": "example"},
    }

    written = apply_config_plan(workspace, plan, dry_run=False, create_backups=True)
    assert len(written) == 2

    root_config = json.loads((workspace / "openclaw.json").read_text(encoding="utf-8"))
    profile_config = json.loads((workspace / "auth/profiles/default.json").read_text(encoding="utf-8"))
    assert root_config["provider"] == "openai"
    assert profile_config["name"] == "default"


def test_apply_config_plan_merges_existing_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "openclaw.json"
    target.write_text(json.dumps({"provider": "anthropic", "tools": {"elevated": {"enabled": False}}}), encoding="utf-8")
    plan = {"openclaw.json": {"tools": {"elevated": {"enabled": True}}}}

    apply_config_plan(workspace, plan, dry_run=False, create_backups=True)

    merged = json.loads(target.read_text(encoding="utf-8"))
    assert merged["provider"] == "anthropic"
    assert merged["tools"]["elevated"]["enabled"] is True
    assert (workspace / "openclaw.json.bak").exists()
