# Session handoff — DragonClaw clean slate

**Written from:** Cursor chat in `dragonclaw_project` workspace (June 2026)  
**Transcript backup:** `/Users/captain/.cursor/projects/Users-captain-dragonclaw-project/agent-transcripts/6842229f-a23c-4102-86d0-f197c19ad242/6842229f-a23c-4102-86d0-f197c19ad242.jsonl`  
**Prototype (read-only):** `/Users/captain/dragonclaw_project`  
**This repo:** first public DragonClaw — **not** a sequel; prototype never shipped.

**Latest session transcript:** `/Users/captain/.cursor/projects/Users-captain-dragonclaw/agent-transcripts/42c2554b-d808-44d3-9159-8b79ed7e3844/42c2554b-d808-44d3-9159-8b79ed7e3844.jsonl`

---

## Pause / resume (Jun 2026)

**Status:** Phase 2 in progress — DC-owned Setup OpenRouter implemented in code; **live E2E on dev machine not re-run** after `dc_catalog` landing.

### Shipped (this pause)

| Area | What |
|------|------|
| Catalog | [`src/dragonclaw/dc_catalog/`](src/dragonclaw/dc_catalog/) — OpenRouter live `GET /api/v1/models`; registry ready for more adapter classes |
| Flow | [`build_model_provider_flow()`](src/dragonclaw/flow_registry.py) — generic `flow.model.<provider>`; hub lists **OpenRouter only** (`pid != "openrouter"` gate in `_load_model_provider_flows`) |
| Model pick | `oc_interactive` configure **removed**; [`dc_menu` model_pick](src/dragonclaw/flow_engine.py) + manual id + key typo inspect ([`flow_model.py`](src/dragonclaw/flow_model.py)) |
| Catalog chain | [`catalog_for_provider()`](src/dragonclaw/model_list.py): DC adapter → OC bridge → `models list` |
| Tests | **110** pytest passing (`pip install -e ".[dev]" && pytest` or `.venv/bin/pytest tests/`) |

### Resume here (priority)

1. **Manual E2E** — valid OpenRouter key → full `dc_menu` catalog (≥50 models) → `models set` → validate + `models status` probe.
2. **Multi-provider hub** — drop OpenRouter-only gate in [`flow_registry.py`](src/dragonclaw/flow_registry.py); add `openai_compatible` adapter entries (Groq, etc.).
3. **Mined catalogs** — `release-gate` → `artifacts/model_catalog_<provider>.json` for static fallback tier (prototype [`docs/model_catalog.md`](file:///Users/captain/dragonclaw_project/docs/model_catalog.md)).
4. **Phase 3** — doctor+ planner loop (SPEC Phase 3).

### Not in scope yet

- `oc_interactive` for model/provider (rejected) or channels (deferred).
- Porting OC runtime provider plugins — DC owns **setup layer** only.

---

## Why this repo exists

The prototype (`dragonclaw_project`) explored an AI-powered OpenClaw installer/configurator/doctor. It accumulated the wrong architecture: reimplemented OC configure flows in Python, fake success criteria, and incremental patch-driven development that cannot scale to full OC coverage.

**Decision:** New public git + HF (when needed). Zero prototype product code in this tree. Salvage ~15–25% of prototype value deliberately (validate gate, OC CLI tools, mining, artifacts). See [docs/prototype.md](docs/prototype.md).

---

## Origin story (product motivation)

~two days with Sonnet/Gemini trying to fix OpenClaw config. `openclaw.json` sent countless times; models rewrote the whole file; every paste was broken or useless. Sometimes keys were sent too. The models sounded authoritative but had **no OpenClaw authority** — no `openclaw config validate`, no live workspace, no structured doctor output.

A concrete example: OpenRouter failed for hours because a key copied via Google Docs had a capital `S` (`Sk-or-...` vs `sk-or-...`). Chat models could not diagnose that. A local agent that can **read auth files** and **run probes** can.

OpenClaw's own doctor also failed repeatedly — fixed checks, shallow fixes, no conversational loop. DragonClaw is **not** "Python scripts smarter than an LLM." It is **LLM reasoning + OC CLI as ground truth + validate gate** so the agent cannot ship confident nonsense.

Adjacent anecdote: a Stairwell builder ([stairwell.run](https://www.stairwell.run/)) had Claude Code edit `openclaw.json` rather than fight OC wizards. DragonClaw productizes that pattern with validate-before-apply and OC-native tools — self-contained for users without a coding-agent subscription.

---

## What the prototype got wrong

1. **`channel_setup` reimplementation** — mined `setup_steps` into Python flows; WhatsApp "success" was only `channels.whatsapp.enabled: true`, not linked. Checklist and onboarding lied.
2. **"Never delegate to `openclaw configure`"** — tried to replace OC UX instead of orchestrate it.
3. **Planner forbids `openclaw doctor`** — forced LLM to guess like remote chat.
4. **Per-step OK? confirmations** — tedious; users want "do X" and it gets done.
5. **LoRA on config permutations** — teaches `config_patch` habit; fights tool-using agent design.
6. **Incremental AI dev without parity matrix** — symptom-driven patches, false confidence from pytest mocks; Mac Mini B1 (pull + `pip install` + `dragonclaw` only) exposed real failure.

---

## Agreed architecture: hybrid agent

DragonClaw is a **domain-specialized AI agent** that:

- Offers **fixed UI flows** (menus, onboarding phases) — not a raw prompt dump.
- **Orchestrates OpenClaw CLI** where OC already solved the problem (configure, onboard, channels link, doctor, models list).
- Uses **four step kinds** in a flow registry:
  - `dc_menu` — DragonClaw menus / prompts (conversation frame).
  - `oc_json` — non-interactive OC CLI; parse JSON/text (e.g. `models list --provider openrouter --json`).
  - `oc_interactive` — foreground TTY handoff to OC's scrollable wizards (WhatsApp QR, OAuth, etc.). Needs `openclaw_interactive` runner.
  - `validate_probe` — validate gate + completion probe.
- **Auto-applies** when intent is clear and validate passes — not OK? on every field.
- **Probe-based success** — model works, channel linked, gateway healthy; never `enabled: true` alone.
- **Anti-hallucination contract** — incremental patches or OC commands; no wholesale `openclaw.json` rewrites; validate before every write; backups automatic.

**Doctor+:** LLM interprets `openclaw doctor` + validate errors + local file inspection (auth prefix, wrong keys); loops until fixed or honest blocker. OC doctor is a **tool**, not replaced.

**Catalogs** inform prompts and flow registry — they are **not** executable specs for parallel Python wizards.

---

## Inference (resolved — living detail)

Self-contained clean-room install. DC planner is independent of the user's OC model config.

- **Init:** `probe_local_capability()` on startup.
- **Capable HW:** auto local `meta-llama/Llama-3.2-3B-Instruct` (no LoRA).
- **Weak HW:** menu → OpenRouter BYOK (free-tier model) recommended; user may choose slow local anyway.
- Profile: `~/.openclaw/dragonclaw_inference.json`.
- LoRA only if Phase 3+ evals require it.

Prototype modules: `inference_capability.py`, `inference_profile.py`, `inference_onboarding.py`, `llm_client.py`, `local_inference.py`, `planner_completion.py`.

---

## Mac Mini B1 bar (consumer test)

**Pass:** `git pull` → `pip install -e ".[runtime,dev]"` → `dragonclaw` only (no manual `session reset`, no `rm -rf ~/.openclaw`).

**Must reach:** install → gateway → provider → API key → live OpenRouter model list → **channel actually works** (e.g. WhatsApp linked, not enable-only) → honest checklist.

Prototype **failed** B1 at channel step (Jun 2026).

---

## Channel ship scope (resolved — proposal)

Full catalog ambition (46 providers / 23 channels) via mined registry + `oc_interactive`. **B1 manual bar:** one QR/link channel + one bot-token channel verified. Remaining entries routable, not each manually QA'd.

---

## OpenClaw pin

Pinned against **OpenClaw 2026.6.1** (dev machine). Regenerate via `release-gate` / artifacts on pin bumps; do not ship on stale schema without gate.

---

## Implementation phases (summary)

Full detail in [SPEC.md](SPEC.md). SPEC is a **living proposal** — iterate per phase.

| Phase | Scope | Exit |
|-------|-------|------|
| **0** | SPEC, HANDOFF, prototype doc, cursor rules | Direction agreed — **done** |
| **1** | Kernel + inference init | Contract tests; interactive runner; capability menu — **complete** |
| **2** | Flow engine, model flows | Generic `flow.model.<provider>`; `dc_catalog` live adapters; `dc_menu` model pick; Plan A rejected — **in progress** |
| **3** | Doctor loop, scenario evals | Troubleshoot scenarios pass |
| **4** | Channels via `oc_interactive` | Mac Mini B1 pass |
| **5** | Ship: release-gate, docs, optional LoRA | Public release criteria met |

## Phase 2 UX decisions (Jun 2026)

- **Menus vs freeform:** Hub and flow steps use scrollable `run_dc_select` (filter rows only). **Ask DragonClaw** is a separate menu row → text prompt → intent router — not autocomplete in one widget.
- **Model pick (Plan A rejected):** `oc_interactive` configure handoff breaks validate gate — removed from model flows.
- **Model catalog:** `dc_catalog` adapter classes (OpenRouter: live `GET /api/v1/models`) → `dc_menu` scroll pick + manual id. Fallback: OC picker bridge, then `models list`. OC setup uses static manifest (~3 rows on 2026.6.1) by design — not a broken install.
- **Flows:** `build_model_provider_flow()` factory; hub registers `menu_primary` providers with API-key onboard (OpenRouter today).
- **Session resume:** On `dragonclaw` startup, if OpenClaw **is installed** → **hub** (clear `active_flow_id`, keep checklist). If OC **not installed** → resume in-flow (install/key steps). Chat loop runs `FlowEngine` whenever `active_flow_id` is set (hub pick or resume) — not gated on `should_resume_session()`.
- **DC menu chrome:** Lobster palette (`#FF5A2D` / `#8B7F77` / `#2FBF71`) on hub, pause, api_key, and inference menus — `◇` intro, no `?` qmark, `●` active pointer. `oc_interactive` steps hand off to real OC `@clack`.
- **Global menu chrome:** Ask DragonClaw / Back to hub (in-flow) / Quit on hub and `dc_menu` steps (api_key, etc.).
- **Hub:** registered flows from `list_flows()` only — no validate/doctor stubs (those route via Ask path).
- **P0 fix (Jun 5):** Hub pick no longer loops when OC installed — `should_resume_session()` incorrectly blocked `FlowEngine` after `begin_flow()`.

### E2E gate (Setup OpenRouter on OC 2026.6.1)

1. `dragonclaw` with OC installed → hub first, checklist visible
2. Pick **Setup OpenRouter** → api_key inspect → onboard → **DC live catalog** (not OC configure)
3. `dc_menu` model pick shows full list when key valid (≥50 models from OpenRouter API)
4. `models set` + validate + probe pass; primary is `openrouter/…`

### OC catalog note (Jun 2026)

`openclaw models list` prefers **static manifest** when rows exist (`list.source-plan.ts`); OpenRouter plugin ships 3 hardcoded models. Live fetch exists in `models scan` and DC `dc_catalog`, not OC setup UI. See `dragonclaw catalog-check openrouter`.

---

## Repo disposition

| Repo | Role |
|------|------|
| `~/dragonclaw` (this) | Public product |
| `~/dragonclaw_project` | Prototype archive — read-only reference |
| `akacaptain/dragonclaw_model` (HF) | Prototype experiment — not shipped with this product |
