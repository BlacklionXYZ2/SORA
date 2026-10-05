# GUI settings and managed model reload

- **Changelog attribution: GPT-6 Astra**, as requested by the owner.
- **Implemented / verification completed: 2026-09-28 18:24:55 BST (UTC+01:00).**
- Status: **implemented and verified**, with DFlash and broader hardware acceptance explicitly open.
- Planning attribution preserved: Deepseek V4.1 Flash's settings/reload handoff.

## Implemented changes

- Added a typed, versioned unified settings store and schema-driven field inventory in
  `src/sora/runtime/app_settings.py`. Legacy runtime/llama JSON imports once; originals remain intact.
  Atomic revisioned writes, disk-edit conflicts, malformed-file backup/repair, saved/active value
  comparisons and immediate/model-reload/next-boot effect boundaries are implemented.
- Expanded `src/sora/providers/llama_server.py` for context/GPU/cache/flash/batch/split/MoE/load/SWA
  and speculative modes (MTP, DFlash, EAGLE-3, simple/ngram choices). Draft paths/bounds and cache
  combinations are validated. Requested flags are checked against the installed binary's help.
- Added revision-bound asynchronous model reload, text/voice admission/draining, provider swap,
  fresh authentication, old-model recovery, persistent last-good recovery and repairable startup
  failures. Model reload cannot apply executable, port, source or other boot-only edits.
- Integrated unified preferences into `src/sora/__main__.py`, runtime service, authenticated local
  API settings/projection/reload/projector-discovery routes and generated public schemas. Old Core
  legacy settings paths remain compatible for programmatic callers; the new launcher uses one store.
- Added `clients/desktop_app/ModelSettingsEditor.cs`: editable controls with effect badges,
  GGUF/projector pickers, automatic adjacent-projector detection/ambiguity chooser, Save/Discard,
  Reload confirmation/progress/retry, disk Refresh, and read-only saved-setting inspection.
  Native QA led to action-button/scroll-layout fixes and picker folder/file prepopulation.
- Updated desktop projection parsing and widget lifecycle polling/status. Full-app UI reads Core's
  canonical settings, not a parallel client configuration. Model keys/secrets remain unprojected.
- Updated both launchers with `-Settings` / unified-store precedence. Added the unified template,
  current Settings runbook, supersession notes for old JSON-edit instructions, README guidance,
  dated roadmap update and verification report. No source commit was created.

## Verification

- Repository gate: **388 Python passed / 12 explicit opt-in skipped**; Ruff, strict mypy (199 source
  files), schema freshness, compileall, **7 PWA passed**.
- **34 C# passed**; desktop and widget builds clean. Launcher syntax checks and actual QA launch passed.
- Native GUI: context save → pending → confirmed reload → ready; timeout applies live without reload;
  persistence verified after Core restart; final GGUF selection auto-filled the adjacent projector.
- Real hardware test: 4096 context / flash attention on / q8_0 K and V; auth rotated, old key rejected;
  post-reload image answers **Red** and **Blue**. **1 passed in 23.27 s**.
- Real MTP: adjacent installed draft weights loaded, dialogue succeeded, backend reported
  **158 accepted / 222 generated draft tokens**. This is not a performance benchmark.
- Failure tests: rollback success/failure, startup repair, cancellation cleanup, concurrent reload,
  stale revisions/disk edits, immutable boot settings, strict flags and missing/ambiguous projectors.

## Deliberate limits / next manual checks

DFlash requires a compatible draft/model live test. Other model pairs, multi-GPU/MoE, all cache
formats and diverse DPI layouts remain unverified. RoPE/CPU-affinity/tensor overrides and advanced
ngram tuning are deferred rather than pretending to be functional JSON-only settings. Widget/PWA
editing and unrelated wider settings categories are not included. Normal owner state was not edited;
its first new-version start migrates automatically. QA state is retained locally for evidence.

Detailed evidence: `docs/verification/SETTINGS_EDITOR_AND_MODEL_RELOAD_GPT-6-Astra_2026-09-28.md`.
User guide: `docs/runbooks/SORA_SETTINGS.md`.
