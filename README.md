# DragonClaw

AI-powered OpenClaw installer, configurator, and doctor agent.

**Status:** Phase 2 — flow engine. OpenClaw pin: **2026.6.1**. See [SPEC.md](SPEC.md) and [HANDOFF.md](HANDOFF.md).

Prototype archive (read-only): `/Users/captain/dragonclaw_project`

## First-time setup

From the repo root:

```bash
cd ~/dragonclaw
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `dragonclaw` CLI into the venv. Without this step, `dragonclaw` is not on your PATH.

**Local planner (optional):** if you want the bundled Llama 3B path without OpenRouter BYOK:

```bash
pip install -e ".[runtime,dev]"
```

Without `[runtime]`, first `dragonclaw` run will prompt for cloud vs local (local needs torch/transformers).

## Commands

```bash
dragonclaw              # inference init + interactive setup REPL
dragonclaw validate     # run openclaw config validate on workspace
dragonclaw doctor       # run openclaw doctor (non-interactive)
dragonclaw install      # OpenClaw npm install (dry-run by default; --apply to run)
dragonclaw interactive -- --help   # foreground TTY handoff (oc_interactive)
```

In the REPL, try **setup openrouter** or pick **Setup OpenRouter** from the menu.

## Tests

```bash
source .venv/bin/activate
pytest
```
