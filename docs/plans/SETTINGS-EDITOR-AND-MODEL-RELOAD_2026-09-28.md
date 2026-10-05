# SORA settings editor in the GUI + model reload — handoff plan

Prepared: **2026-09-28 09:31 +01:00 (Europe/London)**
Prepared for: **GPT-6 Astra** (implementer)
Requested by: owner
Planning author: Deepseek V4.1 Flash (read-only survey; no code was changed)

Original handoff status: **plan only — no code changed by the planning author.**
Implementation update, **2026-09-28 18:21:38 +01:00**: the owner settings/model-reload follow-on is
implemented with GPT-6 Astra changelog attribution as requested. See
[`SORA_SETTINGS.md`](../runbooks/SORA_SETTINGS.md) and the
[dated implementation update](archive/SORA_IMPLEMENTATION_PLAN_UPDATE_SETTINGS_2026-09-28.md).
The original survey/attribution below is retained; the update records implemented clarifications
and acceptance limits. Final verification at **18:24:55 +01:00** includes a successful live MTP
functional check; DFlash remains unverified.
Deliverable of this document: enough verified detail that implementation can start without re-deriving
the current state.

---

## 1. Owner requirement (verbatim)

> "Currently settings have to be altered from a json file in the .local folder, they should be editable
> in the GUI and then stored in a json file. Most settings will be LLM related for now, but there will
> have to be a distinction made for when each setting can next take effect (e.g. 'Next time SORA boots'
> or 'On model reload'). This feature will be implemented by GPT-6 Astra later."

And from the owner's original note to ChatGPT, which defines the first content set:

> "The llama config json should be the store for the app's settings. Obviously not all the json
> parameters will be editable in the settings, but important ones should be editable in the SORA
> settings interface like model path (to the gguf since the mmproj will be in the same path), context
> length, cache quantisation, gpu offload, MTP and dflash, flash attention and the such. I shouldn't
> have to go and search for files to change sora's settings, everything should be editable from the GUI."

## 2. Decisions already taken with the owner

| # | Question | Owner's answer |
|---|---|---|
| 1 | Store shape | **One settings file that contains both** the llama/model settings and the runtime settings |
| 2 | MTP / dflash | They **are** the speculative/draft options — keep that vocabulary (`--spec-type draft-mtp`, `draft-dflash`) |
| 3 | When model-tier edits apply | **Stage on save**, then apply when the owner presses **Reload model** (SORA confirms first; dialogue pauses briefly) |
| 4 | Choosing the model | **One GGUF picker** — auto-detect the mmproj in the same folder and validate the pair |
| 5 | Effect labels | **Every editable setting** shows its effect tier on one Settings page |

---

## 3. Current state (verified by reading the files on 2026-09-28)

### 3.1 Two separate stores today

**(a) Runtime settings** — `src/sora/runtime/settings.py`

- `EditableRuntimeSettings`: `version`, `dialogue_backend` (`deterministic` | `openai-compatible`),
  `dialogue_model`, `dialogue_model_folder`, `dialogue_base_url`, `dialogue_timeout_seconds`,
  `worker_count`, `context_max_chars`.
- `SavedRuntimeSettings` (+`revision`), `RuntimeSettingsUpdate` (+`expected_revision`).
- `RuntimeSettingsStore` writes `<state-root>/data/runtime-settings.json` atomically (temp file +
  `os.replace`), 16 KB size limit.
- Effect today: **everything applies on the next Core restart.** `service.py:516-531`
  (`runtime_settings_view()`) exposes `settings_revision`, `active_settings_revision`,
  `restart_required`, `pending_settings`; `POST /api/v1/settings` returns
  `{settings_revision, restart_required}` (`api/routes.py:1292-1311`), with `409 SETTINGS_CONFLICT`
  on a stale `expected_revision`.

**(b) Managed llama.cpp config** — `src/sora/providers/llama_server.py`

- `LlamaServerConfig` fields: `executable`, `model_path`, `mmproj_path`, `port` (18771),
  `context_size` (8192), `gpu_layers` (`auto`), `startup_timeout` (180). Strict model: unknown keys
  rejected, ≤16 KB, paths must be local files, GGUF magic bytes checked, model ≠ projector.
- `command()` emits: `--model --mmproj --host 127.0.0.1 --port --alias sora-local --ctx-size
  --parallel 1 --gpu-layers --no-webui`.
- `ManagedLlamaServer.start()` probes the port, strips inherited `LLAMA_*`/`LLVM_PATH` from the child,
  generates a per-launch API key (**never persisted**), spawns `python -m sora.providers.llama_server
  --worker`, and polls the authenticated `/v1/models` endpoint until ready or `startup_timeout`.
  `close()` closes the child's stdin, waits 15 s, then kills. `_worker()` watches pipe EOF so the
  model dies with Core.
- Read **once at Core start**: `__main__.py:33` (`--llama-config`), `:400-408` (constructs the server),
  `:438` (`managed_dialogue=managed_model is not None`). There is **no reload path**.
- Owner's live file: `.local/llama-server.json`; portable template: `config/llama-server.example.json`.

### 3.2 What happens in the GUI today

`clients/desktop_app/FullAppForm.cs`:

- `SettingsPage()` (:298) is one small grid: Provider, Model, LM Studio folder, Endpoint,
  Timeout, Workers, Context (chars), plus Save / Discard and a read-only JSON pane.
- `MarkSettingsDirty()` (:360) and `SaveRuntimeSettingsAsync()` (:416) → `POST /api/v1/settings`, then
  reports *"Runtime settings saved. Restart Core to activate them."*
- In managed mode the app **disables** model/backend/endpoint/folder editing (`:364-365`, `:376-377`),
  and `stage_runtime_settings()` rejects changes to those four fields
  (`service.py:544-550`) because `--llama-config` owns them.
- Net effect: **every llama.cpp setting is JSON-only**, and the runbook's answer to switching modes is
  *"move/rename `.local/llama-server.json`"* (`docs/runbooks/SORA_LLAMA_CPP.md:86-87`). That is exactly
  the file-hunting the owner wants removed.

### 3.3 What the installed llama.cpp actually supports

`C:/llama.cpp/llama-server.exe` reports `0.2.0-dev`, build 1, commit `e85caa8` (Clang 23.0.0, Windows).
Verified from `--help` on this machine:

- `-c/--ctx-size`, `-b/--batch-size` (2048), `-ub/--ubatch-size` (512)
- `-fa/--flash-attn [on|off|auto]` (default `auto`)
- `-ctk/--cache-type-k`, `-ctv/--cache-type-v` — allowed values
  `f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1` (default `f16`)
- `-ngl/--gpu-layers`, `-sm/--split-mode {none,layer,row,tensor}`, `-ts/--tensor-split`, `-mg/--main-gpu`
- `-cmoe/--cpu-moe`, `-ncmoe/--n-cpu-moe`, `--swa-full`
- `--load-mode` (the `--mlock` / `--mmap` / `--no-mmap` flags are deprecated in favour of it)
- RoPE scaling family, `--keep`
- **Speculative decoding:** `--spec-type` accepts
  `none, draft-simple, draft-eagle3, **draft-mtp**, **draft-dflash**, draft-dspark, ngram-simple,
  ngram-map-k, ngram-map-k4v, ngram-mod, ngram-cache` (default `none`, comma-separated).
  Draft model: `-md/--spec-draft-model/--model-draft`; also `--spec-draft-ngl` (`-ngld`),
  `--spec-draft-type-k/-v` (draft KV types), `--spec-draft-n-max` (3), `--spec-draft-n-min`,
  `--spec-draft-p-min`, `--spec-draft-p-split`.
- **There is no standalone `--mtp` or `--dflash` flag** — the owner's "MTP" and "dflash" are
  `--spec-type` values. Use their vocabulary as GUI labels: `MTP` → `draft-mtp`,
  `DFlash` → `draft-dflash`.

### 3.4 Project conventions the implementation must follow

- `scripts/verify.ps1` runs Ruff, strict mypy (197 sources), generated-contract freshness,
  `compileall`, the Python suite, and the PWA tests. Astra's last run: **377 passed / 11 opt-in
  skipped**, C# `34 passed`.
- Versioned JSON schemas live in `contracts/schema/v1/` (79 files) and are freshness-checked.
- Every change gets a dated changelog entry in `changelog/` (author line included) and, where it is an
  acceptance milestone, a report in `docs/verification/`.
- Runbooks in `docs/runbooks/` are the owner-facing instructions and must be updated, not left stale.
- Current checkout is dirty (**319 entries, 3 commits**) — pre-existing work, unrelated to this plan.

---

## 4. Design

### 4.1 One store

**Recommended location: `<state-root>/data/sora-settings.json`** (today: `.local/manual-test/data/`).
Rationale: the store must be written atomically *and* revisioned together with the state; the existing
revisioned store already lives there; and a project-level shared file would let a QA/alternate state
root silently overwrite the owner's live configuration. See Open Question 1.

Proposed shape (key names for the existing llama fields stay **verbatim** so
`.local/llama-server.json` and the example file migrate unchanged):

```json
{
  "version": 2,
  "revision": 12,
  "dialogue": {
    "backend": "managed-llama",
    "timeout_seconds": 90.0,
    "context_max_chars": 8000
  },
  "llama": {
    "executable": "C:/llama.cpp/llama-server.exe",
    "model_path": "C:/Users/oscar/Desktop/Models/Unsloth/gemma-4-E2B-it-IQ4_XS-GGUF/gemma-4-E2B-it-IQ4_XS.gguf",
    "mmproj_path": "C:/Users/oscar/Desktop/Models/Unsloth/gemma-4-E2B-it-IQ4_XS-GGUF/mmproj-F16.gguf",
    "port": 18771,
    "context_size": 8192,
    "gpu_layers": "auto",
    "flash_attn": "auto",
    "cache_type_k": "f16",
    "cache_type_v": "f16",
    "batch_size": 2048,
    "ubatch_size": 512,
    "startup_timeout": 180,
    "speculative": {
      "types": [],
      "draft_model_path": null,
      "draft_gpu_layers": "auto",
      "draft_cache_type_k": "f16",
      "draft_cache_type_v": "f16",
      "draft_tokens_max": 3,
      "draft_tokens_min": 0
    }
  },
  "external": {
    "model": null,
    "base_url": null,
    "model_folder": null
  },
  "runtime": { "worker_count": 2 }
}
```

Rules:

- **Never persist the generated llama API key** (existing rule, `llama_server.py:88`, `:99-100`).
- Keep `--parallel 1`, loopback-only bind, `--no-webui`, and the `--alias sora-local` contract.
- Keep the strict-model behaviour: an unknown or misspelled key must produce a clear error naming the
  key, never a silent drop.
- Keep a size cap (16 KB is ample) and the atomic temp-file + `os.replace` write.
- The file stays **hand-editable**; Core must not fight the owner. Detect an external edit (content
  hash) and report *"settings file changed on disk — reload to apply"* rather than overwriting it.

### 4.2 Effect tiers (the core of the request)

Three tiers, exposed to the GUI as plain language:

| Tier (API value) | GUI label | Meaning |
|---|---|---|
| `live` | **Takes effect immediately** | Core applies it to the running process on save; nothing restarts |
| `model_reload` | **On model reload** | Needs the owned llama.cpp process restarted; Core stays up; dialogue pauses briefly |
| `next_boot` | **Next time SORA boots** | Needs the Core process restarted (the launcher re-reads the file) |

Core keeps two watermarks beside `active_settings_revision`: `boot_revision` (config the running Core
started with) and `model_revision` (llama config the current child was loaded with). A field is
*pending* when its tier's watermark is older than the saved revision. On a successful reload,
`model_revision = saved_revision`. This replaces today's single `restart_required` boolean and gives
each row in the GUI an honest state.

### 4.3 Settings inventory (v1 scope)

**Model source and paths**

| Setting | JSON key | llama.cpp flag | Tier |
|---|---|---|---|
| Model source: SORA-managed llama.cpp / external endpoint / deterministic | `dialogue.backend` | — | `next_boot` |
| Model GGUF | `llama.model_path` | `--model` | `model_reload` |
| Projector GGUF (auto-detected next to the model) | `llama.mmproj_path` | `--mmproj` | `model_reload` |
| llama-server executable | `llama.executable` | — | `next_boot` |
| Model port | `llama.port` | `--port` | `next_boot` |
| Startup timeout | `llama.startup_timeout` | — | `next_boot` |

**Performance**

| Setting | JSON key | Flag | Tier |
|---|---|---|---|
| Context length (tokens) | `llama.context_size` | `--ctx-size` | `model_reload` |
| GPU offload (`auto` / `all` / 0–999) | `llama.gpu_layers` | `--gpu-layers` | `model_reload` |
| Batch size / physical batch | `llama.batch_size`, `llama.ubatch_size` | `--batch-size`, `--ubatch-size` | `model_reload` |
| Split mode, tensor split, main GPU (advanced) | `llama.split_mode`, `.tensor_split`, `.main_gpu` | `--split-mode`, `--tensor-split`, `--main-gpu` | `model_reload` |
| Keep MoE weights on CPU (advanced) | `llama.cpu_moe`, `llama.n_cpu_moe` | `--cpu-moe`, `--n-cpu-moe` | `model_reload` |
| Load mode (mlock/mmap) (advanced) | `llama.load_mode` | `--load-mode` | `model_reload` |

**KV cache and attention** (this is the pair behind the LM Studio
`V Cache Quantization requires flash attention` failure seen earlier)

| Setting | JSON key | Flag | Tier |
|---|---|---|---|
| Flash attention (`auto`/`on`/`off`) | `llama.flash_attn` | `--flash-attn` | `model_reload` |
| KV cache type K | `llama.cache_type_k` | `--cache-type-k` | `model_reload` |
| KV cache type V | `llama.cache_type_v` | `--cache-type-v` | `model_reload` |
| Full-size SWA cache (advanced) | `llama.swa_full` | `--swa-full` | `model_reload` |

**Speculative decoding — the owner's "MTP" and "dflash"**

| Setting | JSON key | Flag | Tier |
|---|---|---|---|
| Speculative type: Off / MTP (`draft-mtp`) / DFlash (`draft-dflash`) / EAGLE-3 (`draft-eagle3`) / simple / ngram-* | `llama.speculative.types` | `--spec-type` | `model_reload` |
| Draft model GGUF | `…speculative.draft_model_path` | `--spec-draft-model` | `model_reload` |
| Draft GPU layers | `…speculative.draft_gpu_layers` | `--spec-draft-ngl` | `model_reload` |
| Draft KV cache types | `…speculative.draft_cache_type_k/_v` | `--spec-draft-type-k/-v` | `model_reload` |
| Draft tokens min/max | `…speculative.draft_tokens_min/_max` | `--spec-draft-n-min`, `--spec-draft-n-max` | `model_reload` |

Only add a flag to `command()` when it is actually set — never emit `--spec-type` when the list is
empty, and never emit a draft flag without a draft model. Emitting defaults explicitly is a
behaviour change and should be avoided.

**Dialogue and runtime**

| Setting | JSON key | Tier |
|---|---|---|
| Dialogue timeout (s) | `dialogue.timeout_seconds` | `live` |
| Prompt budget (chars) | `dialogue.context_max_chars` | `live` |
| Worker count | `runtime.worker_count` | `next_boot` |
| External mode: model / endpoint / LM Studio folder | `external.*` | `next_boot` |
| llama-server version, active port, resolved model name, whether a projector is loaded | read-only, detected | — |

*Deliberately JSON-only in v1 (state this in the runbook):* RoPE scaling family, `--keep`, ngram
tuning beyond the type selector, CPU affinity/threads, `--override-tensor*`. The owner accepted that
"not all the json parameters will be editable".

### 4.4 Core API

**`GET /api/v1/projections/settings`** — extend the existing handler (`api/routes.py:1239`):

```json
{
  "saved_revision": 12, "boot_revision": 12, "model_revision": 11,
  "restart_required": false, "model_reload_required": true,
  "model_state": "idle",
  "fields": [
    {
      "key": "llama.context_size", "label": "Context length (tokens)",
      "group": "Performance", "tier": "model_reload", "type": "int",
      "value": 8192, "default": 8192, "min": 2048, "max": 131072,
      "editable": true, "pending": false, "flag": "--ctx-size",
      "help": "Prompt context tokens passed to llama.cpp as --ctx-size."
    }
  ]
}
```

A **declarative `fields` list** is the key design choice: the C# UI renders controls from `type`
(`bool` | `enum` | `int` | `float` | `string` | `path-gguf` | `path-dir` | `path-exe`), `choices`,
`min`/`max` and `tier`. Future LLM settings then need **no C# change**, which matters because the
owner expects this list to grow.

**`POST /api/v1/settings`** — accepts the merged editable subset, keeps `expected_revision` optimistic
concurrency (`409 SETTINGS_CONFLICT`), validates each field against its bounds/allowed values, writes
atomically, bumps the revision, and returns per-tier outcomes plus which watermark advanced:

```json
{ "settings_revision": 13, "applied_live": ["dialogue.timeout_seconds"],
  "model_reload_required": true, "restart_required": false }
```

In managed mode the four-field blanket rejection (`service.py:544-550`) is replaced by tier logic:
llama fields become editable (this is the feature), external fields stay `next_boot`.

**`POST /api/v1/model/reload`** — new, owner-authenticated, loopback only:

1. Reject with `409` if a reload is already running; `422` if the mode is not managed llama or the
   saved llama section is invalid.
2. `model_state = "reloading"` (published through the existing event/state path so both clients show it).
3. Quiesce dialogue: finish any in-flight turn within the dialogue timeout; refuse new turns with a
   clear "model reloading" status. Never silently fall back to another provider.
4. `ManagedLlamaServer.close()` on the old child (stdin → 15 s → kill), then start a new child from the
   saved config, reusing the existing readiness poll, port-bind probe, log path and per-launch key.
5. Rebuild the dialogue provider (new port/key) and swap it into the live dialogue holder.
6. `model_revision = saved_revision`, `model_state = "ready"`, write `sora-settings.last-good.json`.
7. On failure: `model_state = "failed"` with the llama-server log tail, then **automatically restart the
   last-known-good config** so the owner is not left without a model, and report both facts. If the
   rollback also fails: `model_state = "down"` and dialogue reports model-unavailable plainly.

Implementation note: `RuntimeConfig` is assembled at boot and read widely, so do **not** mutate it.
Introduce a small swappable dialogue handle (provider + base_url + model + key + timeout) consulted
per dialogue turn; keep `config` for boot-time facts.

### 4.5 GUI (desktop app)

- Rebuild `SettingsPage()` into a scrollable page (or sub-tabs) with groups: **Model source**,
  **Model & projector**, **Performance**, **KV cache & attention**, **Speculative decoding (MTP /
  DFlash)**, **Dialogue**, **Runtime**, plus the existing read-only JSON pane showing the merged file.
- Render rows generically from the projection's `fields` list; a **tier badge** on every row
  (`Immediate` / `On model reload` / `Next SORA boot`) with a tooltip stating the consequence.
- Top-of-page summary: *"3 saved changes — 2 need a model reload, 1 needs a restart"*, with the
  **Reload model** button enabled only when model-tier changes are pending (and never during a reload).
- Keep Save / Discard and the dirty tracking. Save must state the tier outcome
  ("2 changes saved — press Reload model to apply") instead of the current blanket "Restart Core".
- **GGUF picker**: `OpenFileDialog` filtered to `*.gguf`; on selection scan the same folder for
  `mmproj*.gguf` — exactly one → fill both paths; none → clear error; several → let the owner choose
  from a dropdown. Show the resolved pair and let Core validate on save (paths exist, GGUF magic,
  model ≠ projector). Be explicit in the UI that *projector compatibility can only be proven by
  loading the model*, not by header checks.
- Managed mode: llama fields editable (new), external fields shown as "used when model source is
  external · next boot".
- Reload UX: confirmation dialog ("Dialogue will pause for a few seconds"), progress state, and on
  failure the error plus the log tail and a "rollback applied" note.
- Widget: show a compact state line (model ready / reloading / failed) if it already has a status
  surface; no settings editing there in this update.

### 4.6 Migration and launchers

- First start with the new build: if `data/sora-settings.json` is absent, build it from
  `data/runtime-settings.json` (runtime fields) + the llama file (`--llama-config`, `-LlamaConfig`, or
  the auto-detected `.local/llama-server.json`). Write atomically, **leave the originals untouched**,
  and log the migration.
- If the merged file exists and the legacy files differ, the merged file wins and the ignored file is
  named loudly in the log and in Settings — never a silent divergence.
- `--llama-config` keeps working (explicit path); add `--settings` for the merged file; keep detecting
  the legacy filename and migrate it once. Update `scripts/start-manual-test.ps1:41-48`,
  `Start-SORA.ps1`, and `config/llama-server.example.json` (rename to `sora-settings.example.json`,
  keeping a compatible llama-only example for the standalone path).
- Update `docs/runbooks/SORA_LLAMA_CPP.md` (the "edit the JSON and restart" and "move/rename
  .local/llama-server.json" guidance is superseded) and add `docs/runbooks/SORA_SETTINGS.md`
  documenting every key, its tier, and which keys stay JSON-only.

---

## 5. Failure modes to handle explicitly

| Situation | Required behaviour |
|---|---|
| Reload requested, new GGUF unloadable / projector mismatched | Keep/restore a working model, `model_state = failed`, show the log tail; never a silent substitution |
| Port occupied by another process | Fail the reload with a clear message; never attach to an unknown server |
| Core killed mid-reload | The pipe-EOF supervisor must still reap the child (existing guarantee, must not regress) |
| Dialogue turn in flight when reload starts | Finish within the timeout or fail with a retryable status; no half-answers |
| Settings file edited by hand while Core runs | Detect and report; do not overwrite the owner's edit |
| Model-tier edit saved but never reloaded | GUI keeps showing it as pending (watermark logic), including after a client restart |
| Bad model-tier default at boot | Fail loudly at startup, as today (`--llama-config` behaviour) |
| Secret leakage | The generated llama key never reaches the settings file, the projection, or logs |

## 6. Test plan

**Python** (extend `tests/`):

- Validation per field: bounds, enums (cache types, flash attention, spec types), GGUF magic,
  model ≠ projector, draft flags rejected without a draft model.
- Tier map completeness: every field in the declarative list has a tier, and every writable key is
  reachable — a table-driven test so new settings cannot ship unlabelled.
- Migration from both legacy files; merged file wins; originals untouched; atomic write; size cap.
- Watermarks: save → `model_reload_required` true, `restart_required` false; reload → `model_revision`
  advances, `pending` clears; boot → both watermarks equal the saved revision.
- Conflict: stale `expected_revision` → 409.
- Reload state machine: success, failure with rollback, rollback failure, concurrent reload → 409,
  dialogue refused with a retryable status while reloading.
- Regression: the four-field managed-mode rejection is gone, and external-preferences preservation
  (`service.py:564-573`) still holds.
- Contract freshness: regenerate `contracts/schema/v1/` output so `scripts/verify.ps1` stays green.

**C#** (`clients/csharp_tests/`):

- Projection parsing of `fields`, tiers, watermarks; badge/state mapping.
- Picker: auto-detect one/zero/many mmproj outcomes.
- Save message reflects tier outcome; reload button enablement; disabled during reload.

**Integration / opt-in hardware** (extend `tests/providers/test_managed_llama_server.py -k live`,
gated by `SORA_TEST_LLAMA_CONFIG` as today):

- Reload with a real model: the running command line and `logs/llama-server.log` show the new
  `--ctx-size` / `--flash-attn` / cache types; the endpoint serves afterwards; the port is released on
  shutdown.
- Assert no API key appears in the settings file.

**Owner manual acceptance:** change one setting per tier from the GUI and confirm the badge, the
pending summary, the reload prompt, and the actual effect (dialogue answer after reload; restart
required message for a next-boot field).

## 7. Deliverables list for the implementation

1. `src/sora/runtime/settings.py` (merged store, tiers, watermarks), `src/sora/providers/llama_server.py`
   (extended config + reload), `src/sora/api/routes.py` (projection, update, reload), `src/sora/__main__.py`
   (`--settings`), `src/sora/runtime/service.py` (tier logic + swappable dialogue handle).
2. `contracts/schema/v1/` additions + regenerated artefacts.
3. `clients/desktop_app/FullAppForm.cs` (+ any shared model file) and C# tests.
4. `scripts/start-manual-test.ps1`, `Start-SORA.ps1`, `config/sora-settings.example.json`.
5. `docs/runbooks/SORA_SETTINGS.md` (new), `docs/runbooks/SORA_LLAMA_CPP.md` (update),
   `docs/verification/<date>_SETTINGS-EDITOR…md`, `changelog/<timestamp>_…_GPT-6-Astra.md`.
6. `SORA_IMPLEMENTATION_PLAN.md`: record the new work (proposed **P16 — Owner settings editor and
   model reload**; confirm numbering with the owner).

## 8. Suggested implementation order

1. Merged store + schema + migration + tiers (no behaviour change yet; also wire `boot_revision`).
2. Extended llama config → `command()` flags; unit tests; contract regeneration.
3. Reload machinery in Core + `POST /api/v1/model/reload` + state machine + rollback.
4. Projection `fields` list and the settings-update tier logic.
5. C# generic renderer, tier badges, GGUF picker, reload button/state.
6. Launchers, example config, runbooks, verification report, changelog.
7. Live verification (opt-in hardware test + manual acceptance) and `scripts/verify.ps1`.

## 9. Out of scope

- Widget/PWA settings editing or full cross-client parity (P15.7 remains open elsewhere).
- Non-LLM settings surfaces (capture, vision, avatar/animation, permissions) — the tier mechanism is
  built to accept them later.
- Automatic VRAM fitting / auto-tuning, model downloading, multiple simultaneous model instances.
- Zero-interruption model swapping: a brief dialogue pause during reload is accepted.
- Making *every* JSON key editable — advanced keys stay JSON-only by the owner's own wording.

## 10. Open questions for the owner (small, non-blocking)

1. **Store location** — `<state-root>/data/sora-settings.json` (recommended; keeps QA roots isolated)
   or one project-level `.local/sora-settings.json` shared by every state root?
2. **Model-source switch in the GUI** (managed llama ↔ external LM Studio endpoint) — include in this
   update? Recommended yes; it removes the last "go edit/rename a file" step in normal use.
3. **Advanced keys** — is it acceptable that tensor split, RoPE scaling, load mode, `--keep` and the
   ngram tunables stay JSON-only in v1?
4. **Phase label** — is "P16" the right slot in `SORA_IMPLEMENTATION_PLAN.md`?

## Appendix A — verified flag reference (installed build `0.2.0-dev`, `e85caa8`)

```text
-c,  --ctx-size N            default 0 (from model)
-b,  --batch-size N          default 2048
-ub, --ubatch-size N         default 512
-fa, --flash-attn            on|off|auto   (default auto)
-ctk,--cache-type-k TYPE     f32,f16,bf16,q8_0,q4_0,q4_1,iq4_nl,q5_0,q5_1 (default f16)
-ctv,--cache-type-v TYPE     same values (default f16)
-ngl,--gpu-layers            N | auto | all
-sm, --split-mode            none|layer|row|tensor
-ts, --tensor-split          N0,N1,...
-mg, --main-gpu INDEX
-cmoe,--cpu-moe              (flag)          -ncmoe,--n-cpu-moe N
--swa-full                   (flag)          --keep N
--load-mode                  replaces --mlock/--mmap/--no-mmap
--spec-type                  none,draft-simple,draft-eagle3,draft-mtp,draft-dflash,
                             draft-dspark,ngram-simple,ngram-map-k,ngram-map-k4v,ngram-mod,ngram-cache
                             (default none; comma-separated)
-md, --spec-draft-model      draft GGUF path
-ngld,--spec-draft-ngl       draft GPU layers
-ctkd/--spec-draft-type-k, -ctvd/--spec-draft-type-v      draft KV cache types
--spec-draft-n-max (3), --spec-draft-n-min, --spec-draft-p-min, --spec-draft-p-split
```

Note: `--mtp` and `--dflash` do **not** exist as separate flags in this build.
