# GUI-1d shared voice progress — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-04 03:11:17 +01:00**, Europe/London. Status: **implemented slice / GUI-1d in progress**. No full-stage completion date/time.

## Implemented changes

- Added shared-session local voice polling independent of panel visibility, nullable current/stale/unknown capture status, fixed typed actions, state/static-policy preflight, Core-epoch/async revision guards and pending-mutation/Quit flags. No extra timer/connection/audio/runtime/store.
- Added VoicePanel with explicit Start, mouse/Space hold-to-talk, release-to-send, focus/capture/hide discard, output-only stop, full voice stop and explicit Close worker. Retained hold intent handles release overtaking Begin and refuses retargeting to a new Core. Opening/closing normally only shows/hides; actual audio lifecycle remains Core-owned.
- Added worker/bridge microphone_open metadata independent of general voice state and capture-close finally handling after abort failure. Added stop_output via existing worker stop_speaking(cancel_generation=False), keeping capture/generation/response task intact. Owner-local/static/remote boundaries remain unchanged.
- Added tray recording/closed/unknown icon/text, bounded actual device-key/channel/index inventory with ambiguity labels, independent dialogue-model readiness, voice host/menu/Chat/IPC/root/full launch entries and11th UI-only placement key. Device/config editing stays canonical GUI-2 work, not another settings file.
- Corrected Space handling in new/compatibility voice forms so KeyDown does not suppress the KeyUp needed for release. Added21 C# cases/four Python tests, roadmapv1.18, runbook and detailed verification. Original references/history/model attribution retained.

## Verification and boundary

**231 C# passed**, **710 Python passed /25 opt-in skipped in86.13s**, **8 PWA passed**, mypy267/lint/schema/compile, final three zero-warning/error builds and effect-free launcher forwarding includingVoice. [Verification record](../docs/verification/GUI1_VOICE_GPT-6.1-Sol_2026-10-04.md) distinguishes corrected intermediate issues and final-source checks from native acceptance.

No owner microphone, speaker, voice process, model, paid provider or real spoken turn was used. New HTTP actions use isolated mocked audio; no GUI setup policy bypass. Owner Core PID52000/start/settings/environment unchanged; AppSettingsv9/default Desktop remain. No reset/commit/force kill.

GUI-1d remains open for native hold/release/hide/tray/latency/Quit and physical spoken/model/mouth/device acceptance. Unconfirmed closure is Unknown with explicit recovery, not claimed immediate hardware safety; recording is bounded by the existing configured worker limit. Earlier gates remain open. Next implementation: GUI-2 full Settings; Memory/scheduler/graph/ordinary release still required.

## Source groups

Shared host: new `VoicePresentation.cs`, `VoicePanel.cs`, `ShellSession.cs`, `ShellHost.cs`, Chat/menu/profile/IPC/preference/placement files. Compatibility: `desktop_widget/VoiceForm.cs` Space handling. Launchers/verifier: root/full ShellPanel voice support.

Core: `api/routes.py`, `voice/windows_bridge.py`, `voice/windows_worker.py`. Tests: new `clients/csharp_tests/ShellVoiceTests.cs`, project link, new `tests/voice/test_gui_voice_controls.py`.

## Preservation read-back

**2026-10-04 03:14:31 +01:00:** all103 local documentation links resolve, all9 original reference/draft/overview sizes/hashes match, and exactly3 original completion checkboxes/timestamps remain. No stage-completion time added.
