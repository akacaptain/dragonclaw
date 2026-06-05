# Prototype archive reference

**Path:** `/Users/captain/dragonclaw_project`  
**Role:** Read-only reference for salvage and archaeology. **No code from prototype ships in this repo** except deliberate Tier A ports listed below.  
**OC pin:** 2026.6.1  
**Git:** archive on GitHub (private) when ready; keep local copy for agent file reads.

---

## Why prototype was abandoned

The prototype reimplemented OpenClaw setup UX in Python (`channel_setup`, onboarding phase machine, duplicated configure menus) instead of orchestrating OC CLI. It produced fake success (WhatsApp `enabled: true`), forbade `openclaw doctor` in the planner, and relied on incremental patch QA that cannot cover 46 providers × 23 channels.

---

## Tier A — port to new repo (Phase 1+)

Copy/adapt; do not symlink. Update imports and layout to match new package structure.

| Module | Prototype path |
|--------|----------------|
| Config validate | `src/dragonclaw/openclaw_validate.py` |
| Config apply / backups | `src/dragonclaw/config_apply.py` |
| Config repair helpers | `src/dragonclaw/config_repair.py` |
| OC CLI runner (non-interactive) | `src/dragonclaw/openclaw_tools.py` |
| Workspace snapshot | `src/dragonclaw/workspace_context.py` |
| npm installer | `src/dragonclaw/installer.py` |
| Bootstrap / workspace | `src/dragonclaw/bootstrap.py` |
| Terminal UI | `src/dragonclaw/presentation.py` |
| Capability probe | `src/dragonclaw/inference_capability.py` |
| Inference profile | `src/dragonclaw/inference_profile.py` |
| Inference onboarding menu | `src/dragonclaw/inference_onboarding.py` |
| Remote completion (BYOK) | `src/dragonclaw/llm_client.py` |
| Local completion (base 3B) | `src/dragonclaw/local_inference.py` |
| Planner backend switch | `src/dragonclaw/planner_completion.py` |
| Config merge helper | `src/dragonclaw/configurator.py` |
| Provider onboard pattern | `src/dragonclaw/provider_onboard.py` |
| Artifact sync | `src/dragonclaw/artifact_bundle.py` |
| Release gate | `src/dragonclaw/release_gate.py` |
| Catalog miners | `src/dragonclaw/*_mine.py`, `configure_wizard_catalog.py`, `channel_catalog.py`, `provider_catalog.py`, `model_catalog.py` |
| Pinned JSON | `artifacts/schema.json`, `channel_catalog.json`, `provider_catalog.json`, `configure_wizard_catalog.json`, `model_catalog_*.json` |

**Tests to port with Tier A:**

| Test | Prototype path |
|------|----------------|
| Validate | `tests/test_openclaw_validate.py` |
| Config apply | `tests/test_config_apply.py` |
| OC models contract | `tests/test_openclaw_models_contract.py` |
| Openclaw tools | `tests/test_openclaw_tools.py` |
| Release gate (maintainer) | `tests/test_release_gate.py` |
| Installer | `tests/test_installer.py` |
| Inference profile | `tests/test_inference_profile.py` (port/adapt) |
| Inference capability | `tests/test_inference_capability.py` (port/adapt) |

**New in Phase 1 (not in prototype):** `openclaw_interactive.py` — foreground TTY runner for `oc_interactive` steps.

**Adapt on port:** `local_inference.py` — base instruct default, no LoRA; `inference_profile.py` — OpenRouter free-tier default for remote BYOK path.

---

## Tier B — ideas only; rewrite in new repo

| Asset | Prototype path | Use |
|-------|----------------|-----|
| Smart assistant pivot | `docs/smart_assistant_pivot.md` | Tools + validate north star |
| MVP intent | `docs/mvp_spec.md` | Superseded by `SPEC.md` |
| Model catalog policy | `docs/model_catalog.md` | Source priority for `oc_json` model lists |
| Scenario eval runner | `src/dragonclaw/scenario_eval.py`, `tests/scenarios/` | Framework; replace gold labels |
| Planner response schema | `src/dragonclaw/planner_response.py` | Action JSON contract |
| Session store | `src/dragonclaw/session_store.py` | Rewrite with probe-based checklist |

---

## Tier C — do not port (reference only)

| Asset | Prototype path | Reason |
|-------|----------------|--------|
| Channel setup flow | `src/dragonclaw/channel_setup.py`, `channel_setup_steps.py` | Stub steps, fake success |
| Runtime CLI monolith | `src/dragonclaw/runtime_cli.py` | Wrong structure; replace with thin entry + flow engine |
| LLM planner policies | `src/dragonclaw/llm_planner.py` | Forbids doctor; replace-OConfigure mindset |
| Guided nav / duplicated menus | `src/dragonclaw/guided_nav.py` | Flow registry + OC handoff instead |
| Onboarding completion | `src/dragonclaw/onboarding.py` | `enabled: true` channel done |
| Permutation training | `src/dragonclaw/training_data.py` | Hallucination habit |
| Architecture policy | `docs/architecture_policy.md` | Contradicts hybrid; replaced by `.cursor/rules/` |
| LoRA default ship | `src/dragonclaw/fine_tune.py`, `model_resolve.py` | Defer; prototype adapter is wrong behavior |

---

## Prototype failures to avoid repeating

1. **WhatsApp B1:** catalog step only set `enabled: true`; instructed user to use gateway UI separately; checklist showed ✓.
2. **Session staleness:** mid-onboarding session survived workspace wipe (partially fixed in prototype `513766e` — do not reintroduce).
3. **Numbered menus at 250+ models:** need `oc_json` + scrollable `oc_interactive`, not `render_choice_menu` cap.
4. **pytest false confidence:** mocks passed while Mac Mini manual failed.

---

## Maintainer commands (prototype)

For re-mining artifacts when bumping OC pin:

```bash
# From prototype — reference only until dragonclaw-build exists in new repo
dragonclaw-build release-gate /path/to/openclaw/source <version> [--live]
```

Port `dragonclaw-build` CLI in Phase 1 or early Phase 2 with release-gate.

---

## Hugging Face

| Repo | Status |
|------|--------|
| `akacaptain/dragonclaw_model` | Prototype experiment — mark archived; not used by this product |
| New planner adapter | Create only after Phase 3+ eval bar if base+tools insufficient |
