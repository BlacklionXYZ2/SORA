# W5 — Windows local voice bridge and shared controls

Contributor attribution: **GPT-6.1 Sol**
Implementation slice completed: **2026-10-03 01:07:47 +01:00 (Europe/London)**.
Status: **implemented and verified within the evidence below; W5 remains in progress**.

## Changes implemented

- Added optional pinned faster-whisper/Kokoro/sounddevice dependencies in `pyproject.toml`
  and `uv.lock`. Added `scripts/setup-local-voice.ps1` and `-SetupVoice` to both launchers.
  Speech runs in separate `.local/voice-runtime`. Setup can download software packages;
  speech weights are never downloaded automatically.
- Added `src/sora/voice/settings.py` and shared settings **v6**: interpreter/model paths,
  device keys, voice name, speed and recording limit. V5 migration backs up original JSON.
  Updated schema/projection/example and picker types. Saving voice preferences stops the
  old worker; Start voice loads the new selection.
- Added `windows_audio.py`: bounded mono 16 kHz PCM, local CPU-int8 Whisper, word timestamps,
  silence/no-speech rejection and word-probability confidence; Kokoro 24 kHz chunking and
  actual sounddevice playback. Silent intervals retain their timing. Missing/ambiguous
  configured devices fail visibly instead of silently substituting another device.
- Added `windows_worker.py`: private JSON pipe, authenticated Core voice transport,
  mic-open-only-on-hold, close-before-transcription, capture limit, interruption and local
  playback. No PCM enters Core HTTP, settings or conversation records.
- Added `windows_bridge.py`, runtime/API lifecycle wiring and owner-local-only
  `/api/v1/voice/local`. Static voice OFF stops the worker. Serialized operations and
  lifecycle epochs reject revocation racing process creation. Pipe EOF, launcher stop
  and Windows Core-handle/pipe watchdog reap the actual child even during native stalls.
  Private diagnostics are bounded, credential-redacted and not persisted/projected.
- Fixed real startup hanging during NumPy native initialization in a background thread;
  native speech libraries now initialize on the worker main thread before model loading.
- Added shared `VoiceForm.cs` to full app/widget: Start, hold/release, Stop, Close audio,
  states and device listing. Closing the window stops the shared worker. Implemented
  keyboard/focus/capture-loss release and begin/release race handling. Repaired clipped
  instructions and added horizontal scrolling for device names.
- Added lifecycle, migration, policy, adapter and hardware tests in
  `tests/voice/test_windows_voice.py`, isolated `scripts/fixtures/voice-gui-core.py`,
  runbook, README note and additive roadmap/plan/tracker evidence.

## Verification

- Final `scripts/verify.ps1`, isolated `.local/frontend-verify-20261003` environment:
  **571 Python passed / 23 opt-in skipped**, 73.81s; **8 PWA passed**. Ruff, mypy
  (235 source files), schema freshness and compileall passed.
- Final dedicated-runtime voice run with both hardware/component flags: **13 passed**,
  11.29s. Actual installed Whisper/Kokoro, mic capture/discard, speaker playback, actual
  worker kernel-handle reaping, parent death, control-pipe EOF with stalled main thread,
  and launch/revocation race included.
- Both Windows clients build with **0 warnings / 0 errors**; **37 C# tests passed**.
- All three changed PowerShell setup/launch scripts parsed successfully.
- Computer Use reviewed isolated full-app Voice entry, Loading/Ready, current devices,
  Stop result, Close audio/window and repaired wrapped layout.
- Owned QA app/Core stopped; no listener on 18788 and no voice worker remained afterward.

## Open gates

Human-spoken GUI prompt through the configured dialogue model and audible answer; real
barge-in/device unplug/reconnect; mouth-frame transport/reset; compact-menu and Settings
picker/save GUI acceptance; ordinary launch/restart/packaging and mixed DPI. Settings GUI
recheck failed twice with Computer Use's unavailable-input-geometry error. Hardware probes
prove PCM capture and successful device playback calls, not what the owner heard or real
user recognition. Ambient input was discarded without transcription/persistence. This
GUI test used an explicitly labelled offline dialogue model. The real worker currently
uses the null mouth sink. W2/W3 and all remaining frontend requirements are unchanged.

[Detailed evidence](../docs/verification/W5_WINDOWS_VOICE_BRIDGE_GPT-6-Astra_2026-10-03.md)
and [usage runbook](../docs/runbooks/SORA_LOCAL_VOICE.md).
