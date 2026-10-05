# W5 — Real playback to VRM mouth presentation

Contributor attribution: **GPT-6.1 Sol**
Implementation slice completed: **2026-10-03 01:34:44 +01:00 (Europe/London)**.
Status: **implemented with packaged-renderer evidence; W5 remains in progress**.

## Changes implemented

- Added private `src/sora/voice/relay.py`: validated begin/frame/reset metadata, bounded
  queues, original worker timestamps, stream identity, monotonic serials, no snapshot/replay
  and overflow reset. No PCM, transcript, durable events or model-callable action added.
- Connected real worker `PipeLipSyncSink` to the existing PCM-amplitude presentation clock.
  Core-owned private stdout carries metadata. Bridge invalidation/unexpected exit resets
  presentation. A new worker receives a new epoch domain.
- Forwarded metadata only on the authorized renderer's existing live WebSocket as
  `embodiment.voice`, separately from commands. No inbound HTTP/WS presentation endpoint
  or public action/schema was added. Static voice OFF still permits a reset to be delivered;
  further frames are suppressed. Existing avatar connection authorization is rechecked.
- Added C# output DTO, serial/age/range validation and separate callback; duplicate/stale
  metadata cannot be treated as an avatar action. Unity processes bounded samples on its
  main thread, rejects invalid continuity, resets on connection loss and handles worker
  epoch restart without reusing old playback identity.
- Connected loaded VRM expressions and added a 350ms mouth-close watchdog during missing
  frames. No phoneme/viseme model or external desktop authority introduced.
- Added opt-in, bounded fixture evidence for desired and actually applied VRM weights.
  Ordinary Core avatar launches already strip evidence environment flags. Evidence contains
  no speech text or PCM. Added packaged-player/speaker integration and renderer tests.
- Fixed non-idempotent `StreamingVoiceClient.close()` found by repeated cleanup.
- Fixed a Windows native audio access violation exposed during interruption testing:
  cancelling an asyncio thread future does not stop native `Pa_WriteStream`. Actual writes,
  stop/abort and close are now serialized; a cancelled write must release its handle before
  close. A deterministic blocking-write regression test covers this ownership rule.
- Updated local voice runbook and additive plan/tracker/roadmap evidence.

## Verification

- Final standard `scripts/verify.ps1` in `.local/frontend-verify-20261003`:
  **575 passed / 24 opt-in skipped**, 76.94s, plus **8 PWA passed**. Ruff, mypy
  (238 source files), contract freshness and compileall passed.
- Final Unity build and PlayMode run: **61/61 passed**, packaged Windows player rebuilt
  after final Unity source/test changes.
- **40 C# tests passed**; both Windows clients build with zero warnings/errors.
- Installed worker/adapter plus relay checks: **15 passed / 1 physical mic probe skipped**
  at that run. Focused client/relay/cancelled-write regression: **24 passed** after the fix.
- Actual speaker + packaged sample VRM integration passed twice consecutively after native
  write-lifetime repair: **1 passed in 27.86s**, then **1 passed in 28.48s**. Completion,
  interruption, simulated output-device loss and session disconnect all reset actual weights.
- Initial playback recorded 92 bounded evidence samples and a peak weight of **0.380**.
  Final record: mouth/desired/applied weights all **0**, neutral, no playback, Disconnected.
  Owned test player exited; subsequent checks found no packaged player or voice worker.

## Acceptance boundaries

The packaged test uses synthetic finalized “Hello SORA.” text and the offline deterministic
dialogue provider, actual Kokoro/PortAudio output and the packaged **sample VRM**. The pipe
sink runs in the test process, with its exact emission forwarded to the relay; this does not
prove a full microphone → child worker → real LLM → GUI session. Device-loss events were
simulated, not physical unplugging. No subjective audibility, measured audiovisual latency,
custom-owner-avatar or new Computer Use GUI acceptance is claimed this turn.

Real-user GUI voice, ordinary restart/setup, actual unplug/reconnect, Settings/compact GUI
and mixed-DPI acceptance remain open. All W2/W3 and other outstanding goal scope is preserved.

[Detailed evidence](../docs/verification/W5_VOICE_MOUTH_INTEGRATION_GPT-6-Astra_2026-10-03.md).
