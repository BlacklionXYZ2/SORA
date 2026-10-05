# GUI-2 read-only launch details — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**, not Astra. Implementation/verification checkpoint: **2026-10-04 07:51:34 +01:00**, Europe/London. Status: **progress / implemented slice**; GUI-2 and the overall GUI goal remain in progress. No stage-completion checkbox/time.

## Changes implemented

- Added optional version1 read-only launch metadata to canonical AppSettings v9 projection: submitted managed-worker capture, saved next-model-reload preview with current boot configuration, and saved next-Core-start preview including boot changes.
- Shared the exact typed argument builder between real launch and preview, and shared the reload candidate blend between admission and preview. Previews perform no file/runtime/model probes and never imply loading.
- Retained immutable submitted argument capture on managed worker submission and cleared it during cleanup. Missing/exited/no-capture/non-managed state is explicit; capture is not OS attestation or inferred GPU capability.
- Added bounded printable closed-grammar validation in Core and the C# read-only formatter. Authentication/environment/logs/private unknown payloads are not serialized or displayed; unknown/duplicate/credential/control/oversized/bad-bind vectors are withheld. No raw-flags editor/executor or new authority.
- Connected the read-only pane to Advanced Settings, including old-Core unavailable and current/stale labels; compatibility Desktop now uses actual connectivity. No extra timer, synchronizer/provider/runtime/settings store.
- Closed an old-draft/equal-revision/new-Core modal Save race by checking the retained epoch before submission, not merely after acknowledgement. Dirty/model-purpose close now observes the latest projection immediately.
- Protected file/folder/inspection/consequence modals from control replacement and host Quit. New-Core projector selection and cancellation retain the draft with truthful outcomes; noneditable browse controls remain disabled.
- Added component/fault tests, roadmapv1.20 and runbook/verification evidence. Preserved all original stage history, completed timestamps, references and other model attribution.

Sources: `src/sora/providers/llama_server.py`, `src/sora/runtime/app_settings.py`; `clients/desktop_app/SettingsLaunchPresentation.cs`, `ModelSettingsEditor.cs`, `SettingsDraftState.cs`, `FullAppForm.cs`; shell/test project links; `tests/providers/test_managed_llama_server.py`, `tests/runtime/test_app_settings.py`, `clients/csharp_tests/SettingsLaunchTests.cs`.

## Verification and limits

**284 C# passed**, **719 Python passed /25 opt-in skipped in87.52s**, **8 PWA passed**; mypy267/lint/generated schema/compile and all three Windows builds warning/error-free; launcher forwarding checks pass. [Detailed evidence](../docs/verification/GUI2_LAUNCH_DETAILS_GPT-6.1-Sol_2026-10-04.md).

No new native render/input/modal/keyboard/device/restart/real-model reload/recovery/provider acceptance claimed. Owner Core PID52000/start time, canonical owner settings, ordinary Desktop launch and owner `.venv` remain unchanged. No reset/commit/material deletion. GUI-2 acceptance remains open; GUI-3a canonical Memory service/browser is the next available implementation, without waiving GUI-0b/GUI-1/GUI-2 gates or GUI-3b/c/GUI-4–GUI-6 scope.
