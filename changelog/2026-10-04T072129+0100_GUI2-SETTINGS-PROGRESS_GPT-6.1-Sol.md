# GUI-2 categorized Settings — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**, not Astra. Implementation checkpoint: **2026-10-04 07:21:29 +01:00**, Europe/London; final source/test/build/preservation checkpoint **07:33:44 +01:00**. Status: **progress / implemented slice**. GUI-2a/b/c/d and the full GUI objective remain in progress; no stage-completion timestamp or checkbox added.

## Changes implemented

- Replaced shared-host read-only Settings with the full canonical editor; retained standalone GUI-0 probe and compatibility clients. One host transport/session/effect slot, no additional poller/provider/store.
- Mapped every84 editable v9 preference to the ten-category GUI; added advanced disclosure, metadata fallback for existing Cores, category information and the exact field-map artifact. Kept original defaults/effect tiers/version/static-policy boundaries unchanged.
- Retained all GGUF/projector/context/cache/GPU/flash/speculation controls, specialist identities/preferences/model purposes, static access/perception/voice, task limits and project/workspace/base-ref controls. Added actual projected model status/details and shared Appearance/Voice/Agents/Paths/Integrations links. Missing memory/scheduler/VRAM/capability data remain explicitly unavailable.
- Added fixed Settings request vocabulary, fresh canonical revision/editable-field validation, profile identity fencing before/after submission, acknowledgement checks, shared mutation serialization and late-read generation protection. No auto-retry or effect replay.
- Added pure draft state, pending-editor locks, dirty/unknown/conflicting reload protection, disposed/cancel checks, and captured-epoch/revision confirmations. Save cannot erase a newer edit; late projector discovery cannot replace another selection/Core.
- Added owner-reviewed draft reconciliation: read current saved values, display previous/current/local edited values, preserve only edited fields, adopt untouched current values, then require separate Save. Explicit discard remains available. No automatic three-way merge or silent untouched-field reversal.
- Closing Settings now hides/retains drafts; native Quit protects pending/dirty Settings and freezes edits during accepted shutdown. Unconfirmed/deferred shutdown keeps the host/editor available. Device-key options use only unique current direction-compatible inventory, retaining typed drafts and default/unknown behavior without opening audio.
- Added model-name verification/field-map artifacts and roadmapv1.19/runbook updates. Preserved prior timestamps, three completed specification entries, original references/overview and other model attribution.

Primary sources: `src/sora/runtime/app_settings.py`; `clients/desktop_app/ModelSettingsEditor.cs`, `SettingsDraftState.cs`, `SettingsCategories.cs`; `clients/desktop_widget/ModelPurposeForm.cs`; `clients/desktop_shell/SettingsForm.cs`, `SettingsRequests.cs`, `ShellSession.cs`, `ShellHost.cs`, `PanelPreferencesBinding.cs`; client project links; `tests/runtime/test_app_settings.py`, `clients/csharp_tests/SettingsDraftTests.cs`, `ShellSettingsTests.cs`.

## Verification and limits

**273 C# passed**, **711 Python passed /25 opt-in skipped in87.53s**, **8 PWA passed**; lint/mypy267/schema/compile passed, all three Windows builds warning/error-free and effect-free launcher verifier passed. [Detailed verification](../docs/verification/GUI2_SETTINGS_GPT-6.1-Sol_2026-10-04.md), [84-field map](../docs/gui/GUI2_SETTINGS_FIELD_MAP_GPT-6.1-Sol_2026-10-04.md).

No new actual native Settings/user-input/physical-device/real-model reload acceptance, provider entitlement, or final reference-style delivery claimed. Sanitized actual launch details and those connected gates remain required, as do GUI-3–GUI-6 and earlier acceptance. Owner Core PID52000/start time retained; ordinary Desktop launch, owner `.venv` and canonical owner settings were not replaced/restarted. No commit/reset/material deletion.
