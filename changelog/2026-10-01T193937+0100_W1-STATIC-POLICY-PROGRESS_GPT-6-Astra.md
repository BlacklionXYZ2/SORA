# W1 static access — GPT-6 Astra

Implementation slice completed: **2026-10-01 19:39:37 +01:00**.
Stage status: **W1 in progress**. This records a verified implementation slice, not W1 or goal completion.

Implemented schema-3 Companion access settings, preserved v2 migration backups and explicit disables, separate recoverable settings snapshots, fail-closed invalid startup access, and schema-driven GUI switches. Introduced an authenticated owner-local operation context without grant/approval records and explicit operation effects, shared consumption/rechecks, policy epoch invalidation and volatile-context cleanup. Connected HTTP and embodiment WebSocket owner authentication. Settings-backed capture/avatar dispatch now use static policy instead of self-minted grants. Attached-file reads and delegation admission check settings. Removed the Content grant-ID field and updated settings-version handling.

Changed implementation areas: src/sora/security/local_policy.py (new), runtime/app_settings.py, runtime/service.py, api/server.py, api/routes.py, voice/sessions.py, embodiment/local_player.py; clients/desktop_app/FullAppForm.cs and ModelSettingsEditor.cs; clients/desktop_widget/FullAppModel.cs; exported app-settings/settings-edit schemas. Added tests/runtime/test_local_policy.py and expanded settings, capture/dialogue and local-player tests. Existing contributor work and attribution were preserved; no commit was made.

Verification: full verify gate 477 passed / 13 opt-in skipped plus 7 PWA tests; final expanded targeted set 30 passed; C# 36 passed; desktop app build zero warnings/errors; final Ruff, mypy 216 files and schema check passed. No paid/live-model run. GUI review was interrupted by the active foreground game/user input before Settings could be inspected; access switches were not clicked. Owned isolated QA processes stopped, QA logs retained, owner runtime untouched.

Known open work includes legacy embedded auto-grants, comprehensive queued-agent/in-flight cancellation, extension/integration effect registration, ordinary startup, full GUI/native/voice/renderer/restart acceptance. See [detailed evidence and limitations](../docs/verification/W1_STATIC_POLICY_PROGRESS_GPT-6-Astra_2026-10-01.md) and [full goal tracker](../docs/verification/FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md).
