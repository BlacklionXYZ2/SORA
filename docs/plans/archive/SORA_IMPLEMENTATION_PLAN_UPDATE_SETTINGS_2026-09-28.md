# Settings editor / model reload — dated implementation update

Recorded: 2026-09-28 18:21:38 +01:00 (Europe/London).
Implementation/changelog attribution requested by owner: **GPT-6 Astra**.

This is an additive snapshot of the settings follow-on; it does not replace the preserved overview
or renumber/reopen completed phases. Source handoff and planning attribution remain in
`docs/plans/SETTINGS-EDITOR-AND-MODEL-RELOAD_2026-09-28.md` (Deepseek V4.1 Flash).

## Implemented and verified

- One state-root-local, revisioned JSON store for model/runtime preferences; atomic writes,
  legacy import with originals retained, external-edit conflict detection, malformed-file backup.
- Schema-backed full-app editor, GGUF picker/projector discovery, effect-tier badges, Save/Discard,
  explicit Reload confirmation/status, retry, disk refresh and read-only saved-settings inspection.
- Context, GPU, flash attention, K/V cache, batching, split/MoE/load/SWA and speculative/draft controls.
- Reload admission, text/voice generation quiescence, per-launch key rotation, old-model recovery,
  last-good snapshot and repairable startup failure; settings stay available without a working model.
- Widget model lifecycle status and launcher support for canonical settings precedence.
- Repository gate: 388 Python passes / 12 opt-in skips, Ruff/mypy/schema/compileall, 7 PWA passes;
  34 C# passes and clean desktop/widget builds. Separate live reload/vision test passed in 23.27 s.
- Native GUI context Save/Reload and immediate timeout edits succeeded and survived Core restart.

## Clarifications applied to the handoff

Pending status compares values, not global revision watermarks. Model reload preserves active
boot-tier executable/port/source settings. Failed startup exposes repairable Settings. Reload is
revision-bound and asynchronous (202), avoiding HTTP/UI timeouts. Raw backend log tails are not
exposed through the GUI. Explicit typed flags make GUI-saved configuration deterministic; runtime
help is probed before unloading a working model. A single speculative mode is selected per load.

Unlisted RoPE/CPU-affinity/tensor overrides and advanced n-gram tunables are deferred, not implemented
JSON-only switches. The editor is intentionally full-app-only; no guest/remote settings authority.
Client placement preferences and permissions/credentials remain separate from model/runtime prefs.

## Boundaries still open

Final addendum, 2026-09-28 18:24:55 +01:00: native picker selection auto-filled the matching projector.
MTP loaded the adjacent Gemma E2B MTP weights and completed dialogue; runtime evidence recorded
158/222 accepted/generated draft tokens. DFlash still needs live acceptance with compatible weights.
No universal backend, multi-GPU, MoE, cache-format or speculative speed/quality claim. Different-model
selection and diverse DPI layouts remain useful owner checks. This update does not close P15.7 four-surface parity, P15.2 phone trust,
or unrelated wider Settings categories.

See `docs/runbooks/SORA_SETTINGS.md` for use and the dated GPT-6 Astra changelog for file/evidence details.
