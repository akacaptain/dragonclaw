# DragonClaw — product specification (draft)

**Status:** Phase 2 — flow engine (living proposal)  
**Prototype reference:** `/Users/captain/dragonclaw_project` (archive only)  
**OpenClaw pin (initial):** 2026.6.1 (via release-gate artifacts)

---

## 1. Problem

OpenClaw users struggle to configure installs: remote LLMs rewrite `openclaw.json` without validation; OC doctor misses real-world issues; hours are lost on hallucinated config.

**DragonClaw** is a local AI agent that installs, configures, and troubleshoots OpenClaw with:

- Access to the real workspace and (with consent) secrets for diagnosis
- `openclaw config validate` on every write
- OpenClaw CLI as hands — orchestrated, not reimplemented wholesale
- Fixed guided flows plus free-text intent — not a blank prompt

---

## 2. Success stories (must support)

| Story | Success criterion |
|-------|-------------------|
| OpenRouter broken for hours | Agent inspects auth/key format, runs probes, minimal fix, validate OK |
| "Setup openrouter" | Menu or NL → fixed flow → auth → model picker (OC JSON or TTY) → primary set → models probe OK |
| Gemini-style JSON hell | Agent cannot apply invalid config; no default full-file rewrite |
| WhatsApp / channel setup | OC interactive link flow; success = **linked**, not `enabled: true` |
| "Fix my setup" | Doctor loop: `openclaw doctor` + validate + LLM interpretation until fixed or clear blocker |
| Clean-room install | `pip install` + `dragonclaw` only; self-healing session where designed |

---

## 3. Non-goals

- Prototype product code in this public repo
- Reimplementing all 9 OC configure sections in Python
- Config permutation LoRA / training on schema field dumps
- Delegating UX by dumping user into `openclaw configure` with no agent frame (handoff without orchestration)
- Per-step OK? on routine setup steps
- Claiming channel success without link/health probe
- Shipping prototype `akacaptain/dragonclaw_model` LoRA as default

---

## 4. Product definition

**One command:** `dragonclaw`

**Roles:**

| Role | Description |
|------|-------------|
| Installer | Node/npm checks, `npm install -g openclaw` |
| Configurator | Provider, model, gateway, channels — hybrid flows |
| Doctor+ | LLM + OC doctor + validate + local inspection |

**Interaction:**

- Guided menus every turn where appropriate; "(or describe in your own words)" always available
- User says "do X" → agent executes (auto-apply after validate / OC exit 0)
- Confirm only for destructive ops: full replace, restore backup, global install overrides

---

## 5. Architecture

### 5.1 Layers

| Layer | Owns |
|-------|------|
| **Session router** | Maps menu picks + NL → `flow_id`; tracks phase/checklist |
| **Flow engine** | Runs ordered steps from flow registry |
| **LLM planner** | Ambiguous intent, doctor reasoning, retry after tool output |
| **OC tools** | Non-interactive CLI + interactive TTY runner |
| **Validate gate** | `openclaw config validate` before apply |
| **Probes** | models status, channel link, gateway health |

### 5.2 Flow step kinds

| Kind | When | Example |
|------|------|---------|
| `dc_menu` | DC-owned picker / prompt | Provider menu, API key prompt |
| `oc_json` | OC exposes machine output | `openclaw models list --provider X --json` |
| `oc_interactive` | OC owns TTY UX | `openclaw configure` section, channel QR |
| `validate_probe` | Gate + done check | validate + channel linked probe |

### 5.3 Flow registry source

Mined artifacts (from `dragonclaw-build release-gate`):

- `configure_wizard_catalog.json` — sections, fresh-install order
- `provider_catalog.json` — providers, auth methods, onboard flags
- `channel_catalog.json` — channel labels; link mechanism → step kind
- `schema.json` — prompt context, not training permutations

### 5.4 Planner default

**Base instruct model + tools first.** Default local model: `meta-llama/Llama-3.2-3B-Instruct` (no LoRA at ship). Optional LoRA later only if scenario evals show gap; train on action protocol + tool choice, not config key permutations.

### 5.5 Inference (proposal — refine per phase)

DragonClaw is **self-contained** in a clean-room install. The DC planner does not reuse the user's OC-configured model.

**On `dragonclaw` initialization:**

1. `probe_local_capability()` — GPU/MPS vs CPU, RAM (8GB+ recommended), runtime deps.
2. **Capable hardware** → auto-select bundled local 3B instruct (no menu).
3. **Weak hardware** → menu: OpenRouter BYOK cloud assistant (recommended) / local anyway (slow warning) / defer key.
4. Profile persisted at `~/.openclaw/dragonclaw_inference.json`.

| Tier | When | Planner model |
|------|------|---------------|
| **Local (default)** | GPU/MPS + sufficient RAM | Bundled `meta-llama/Llama-3.2-3B-Instruct` |
| **Remote BYOK** | CPU-only, low RAM, or user choice | OpenRouter free-tier model (exact id pinned in Phase 1 smoke test) |

Maintainer override: `DRAGONCLAW_USE_REMOTE_API=1`. LoRA deferred to Phase 5+ eval gate only.

**LLM scope:** deterministic flows carry happy-path setup; LLM used for NL routing and Doctor+ interpretation.

---

## 6. Anti-hallucination contract (hard requirements)

1. No config write without `openclaw config validate` success (except emergency restore path, logged).
2. Default mutation = **minimal patch** or **OC CLI command**, not `__replace_file__`.
3. Success messages require **probe proof** documented per flow.
4. LLM **must** use `openclaw doctor` and validate output for troubleshoot — not forbidden.
5. Secrets: local inspection for diagnosis; redact when remote BYOK tier is active.

---

## 7. Acceptance matrix (ship bar)

| Flow | Probe for "done" |
|------|------------------|
| Install OpenClaw | `openclaw --version` on PATH |
| Gateway local | validate OK + gateway probe |
| Provider auth (API key class) | auth file present + `models list` succeeds |
| Model primary | validate OK + primary in config + models probe |
| Channel (WhatsApp class) | linked state per OC CLI/status — not `enabled` only |
| Channel (bot token class) | token set + channel health if available |
| Doctor: unrecognized key | key removed/restored + validate OK |
| Doctor: broken JSON | restore from backup + validate OK |
| Doctor: auth typo | user-visible diagnosis + probe pass after fix |

**Consumer test:** Mac Mini B1 — pull + pip + `dragonclaw` only.

**Channel ship bar (proposal):** B1 verifies one QR/link + one bot-token channel; full mined catalog routable via registry + `oc_interactive` (not each manually tested).

**Automated:** pytest contract tests + scenario evals on tool/doctor behavior (not config permutation accuracy).

---

## 8. Implementation phases

### Phase 0 — Spec

**Deliverables:** `HANDOFF.md`, `SPEC.md`, `docs/prototype.md`, `.cursor/rules/`  
**Exit:** Direction agreed; living SPEC sufficient to start Phase 1.

### Phase 1 — Kernel (complete)

Port from prototype Tier A:

- `openclaw_validate`, `config_apply`, `config_repair`, `configurator`
- `openclaw_tools` + new `openclaw_interactive` (PTY foreground)
- `workspace_context`, `installer`, `bootstrap`, `presentation`
- Inference: `inference_capability`, `inference_profile`, `inference_onboarding`, `llm_client`, `local_inference`, `planner_completion`
- Minimal `pyproject.toml`, package layout, pytest for validate/apply/tools/installer

**Exit:** validate gate works; interactive runner demo'd with `openclaw --help` or configure dry path; installer smoke test; inference capability menu on init.

### Phase 2 — Flow engine (current)

- Flow registry loader from artifacts
- Session router + thin `dragonclaw` entry
- `flow.model.<provider>` for API-key providers (OpenRouter first)
- Auto-apply; probe-based checklist
- Menus: `dc_menu` + `oc_json` model list

**Exit:** "setup openrouter" happy path in dev workspace.

### Phase 3 — Doctor+

- Planner tool loop with doctor + validate
- Scenario fixtures from real OC error strings
- Local auth inspection for diagnosis scenarios

**Exit:** scenario eval suite green (mock); live spot-check with broken configs.

### Phase 4 — Channels

- `oc_interactive` for link flows
- Per-channel completion probes
- Mac Mini B1 manual pass

**Exit:** at least one QR/link channel + one bot-token channel verified on Mini.

### Phase 5 — Ship

- `dragonclaw-build release-gate` on target OC version
- Full manual matrix
- README, consumer install docs
- HF planner repo only if LoRA needed

---

## 9. Repository layout (target)

```
dragonclaw/
  SPEC.md
  HANDOFF.md
  README.md
  docs/
    prototype.md
  .cursor/rules/
  src/dragonclaw/          # Phase 1+
  src/dragonclaw_build/    # maintainer CLI
  artifacts/               # pinned OC JSON
  tests/
```

---

## 10. Review checklist (living)

- [x] Problem/success stories accurate
- [x] Hybrid architecture (orchestrate OC, don't replace) correct
- [x] Auto-apply vs confirm boundaries OK
- [ ] Acceptance matrix — refine per phase
- [x] Phase order and exits make sense
- [x] Inference tier (§5.5) — two-tier proposal
- [x] Provider/channel ship scope — two-class B1 + full registry routing

**Phase 1:** kernel ports per `docs/prototype.md` Tier A.
