# W5 shared voice orchestration — GPT-6.1 Sol

Slice completed: **2026-10-03 00:21:15 +01:00 (Europe/London)**.
Status: implemented and verified for the bounded Core orchestration slice.
W5 and the overall frontend-alignment goal remain in progress.

## Changes implemented

- Final owner-local spoken requests now enter the same companion dialogue path as typed
  requests: native read selection, local file discovery/read, passive context, image handling,
  current avatar keywords, board commands, model scheduling and deadline checks. This shares
  currently implemented capabilities; it does not implement the remaining W3 desktop schema.
- Added an internal commit callback so normal spoken turns use the existing atomic
  `append_voice_turn_once` receipt instead of persisting a text pair and another voice pair.
  The callback is internal, not a caller-controlled HTTP payload. Existing task-planning
  acknowledgements remain separate lifecycle records where planning already creates them.
- Connected voice generation IDs and interruption to the conversation registry. Barge-in,
  settings invalidation and deadlines reject late provider replies, including a provider that
  suppresses cancellation. Shutdown/interruption waits are bounded to two seconds.
- Preserved the durable commit boundary: once an atomic voice receipt starts, interruption
  finishes that receipt and suppresses playback rather than claiming a history rollback.
- Owner-local spoken references use static access without an attention grant. Voice walk
  destinations use the historical cursor at the spoken timestamp, not the later STT pointer.
  Missing/stale samples still require clarification; no delayed-coordinate fallback is added.
- Fixed playback expiry to start after response generation, not before it. Started audio can
  finish after the 30-second admission deadline; queued expired commands remain rejected.
- Advanced the output epoch on speaker loss so a response generated across disconnect/reconnect
  cannot be newly queued after recovery. Its completed text remains available in history.
- Added shared queued/thinking and started/talking status. Both Windows surfaces use the shared
  status label and now render active playback as `Speaking…`, not `Ready to talk`.
- Added voice API error codes for unavailable local files, dialogue timeouts and provider
  unavailability instead of reporting those failures as generic transcript conflicts.
- Added deterministic parity/lifecycle/API tests and an opt-in actual local-model voice-read
  integration test. Updated the plan, roadmap and tracker additively.

## Verification

- Final `scripts/verify.ps1`: **562 Python passed / 19 opt-in skipped**, 69.99s;
  **8 PWA tests passed**. Ruff, mypy (230 source files), schema freshness and compile checks passed.
- Final targeted voice checks: **36 passed / 1 opt-in skipped**, 9.83s.
- Actual managed llama.cpp / **Gemma 4 E2B IQ4_XS**, existing matching F16 projector,
  context 8192 and GPU auto: **1 opt-in test passed**, 10.29s including runtime/model startup.
  A finalized spoken-text event discovered an unattached owned note and answered with its exact
  `VOICE PARITY CHECK PASSED` result and filesystem read evidence. Replay produced no second
  reply/playback. This is actual model/Core integration, not physical microphone evidence.
- Cached isolated speech-runtime probes: faster-whisper 1.2.1 loaded the existing local
  base.en snapshot and transcribed the synthetic SAPI fixture successfully; Kokoro ONNX 0.6.1
  loaded the existing int8 model/voice bank and synthesized 42,496 samples at 24 kHz.
  sounddevice 0.5.5 enumerated input/output devices. No device stream was opened.
- Final **37 C# tests passed**; full app and compact widget builds had zero warnings/errors.
  The new Speaking label has automated coverage, not a fresh live GUI voice review.
- No new model download, paid provider, owner history/settings modification, agent task or
  irreversible desktop effect. Owned test model process closed; the pre-existing unrelated
  Hermes llama-server process was observed and left running.

## Remaining gates

Actual local PCM/device adapters and Windows press-to-talk/playback controls; GUI-visible device
and model configuration; microphone-to-Core-to-speaker acceptance; physical interruption, device
loss and mouth reset; real spoken-time cursor collection; noisy-room/echo behavior; packaging and
ordinary startup; full W3 action schema and W2 delegation/catalogue integration. Existing voice
task-control compatibility paths remain; this is not the final unified action vocabulary.

[Detailed evidence](../docs/verification/W5_SHARED_VOICE_ORCHESTRATION_GPT-6-Astra_2026-10-03.md).

