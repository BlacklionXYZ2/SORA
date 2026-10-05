# Shared voice orchestration evidence — GPT-6 Astra

Slice completed: **2026-10-03 00:21:15 +01:00**, Europe/London.
W5 is in progress. The frontend goal is active, not complete.

## What changed

The old voice finalization called the dialogue provider directly, bypassing the newer native/file
reads, perception, avatar and board paths. Normal finalized owner-local speech now calls the same
companion path as text, with internal spoken-reference context and an atomic voice-receipt commit
callback. Session/device checks still happen first. Non-owner callers do not inherit local read,
board or avatar authority. Static capability changes cancel or reject local precommit work.

Each voice generation has a conversation request ID. Existing voice interruption remains its
session protocol but now cancels the corresponding shared conversation work. Provider cancellation
does not count as sufficient evidence: late replies and elapsed deadlines are checked before commit.
Once the atomic receipt begins, interruption may preserve the completed transcript but suppresses
audio. A stopped effect is not rolled back, and already-attempted effects are not replayed.

Normal finalizations create one user/assistant pair with a durable utterance receipt. Replayed events
do not call the model again or create another playback command. Task planning/delegation can retain
its existing separate acknowledgement records; this report does not claim every action creates only
two total messages. Compatibility stop/steer/cancel/new-work controls have not been replaced by the
future unified schema.

Voice movement uses cursor history at `reference_spoken_at` or `speech_ended_at`, with current
topology/freshness checks. It never falls back to the pointer position after STT finishes. The future
Windows device bridge must supply real timestamps and cursor samples for this to work in the GUI.

## Evidence matrix

| Check | Result | Boundary |
|---|---|---|
| Full regression | 562 passed / 19 opt-in skipped, 69.99s; 8 PWA checks | Final Python source; native/device skips are not implied passes |
| Targeted voice regression | 36 passed / 1 skipped, 9.83s | Shared reads, motion, references, receipts, cancellation, playback and API fixtures |
| Actual local model | 1 passed, 10.29s | Real GGUF/llama.cpp, finalized transcript input, owned synthetic filesystem; no physical audio |
| Unattached local file | Read outside Core root; one pair; zero grants; duplicate suppressed | Deterministic provider verifies actual read context without persisting file body |
| Native window read | Model-selected inventory; source evidence; no image call | Native bridge fixture, not another new OS/GUI window observation |
| Wave/walk | Existing avatar dispatch; walk uses spoken-time sample, not newer cursor | Async avatar fixture, not visible Unity motion |
| Cancellation/revocation | Stubborn late reply rejected after barge-in or voice OFF; no history/audio | Deterministic asynchronous races |
| Commit race | Interrupt during receipt transaction preserves one pair and suppresses audio | Deterministic durable repository test |
| Playback timing | Fresh expiry after simulated 45-second generation; started playback can complete after admission TTL | Controlled clocks and session events |
| Speaker recovery | Disconnect/reconnect during generation yields text but no stale playback | Device-event simulation, not cable/device manipulation |
| Status | Queued thinking, started talking, completed idle; C# Speaking label | Automated Core/client tests; not live audio GUI evidence |
| C# / builds | 37 passed; full app/widget zero warnings/errors | Final shared label and client build compatibility |

The live test used existing `gemma-4-E2B-it-IQ4_XS.gguf` with `mmproj-F16.gguf`, context 8192,
GPU auto and a dynamically selected free loopback port. It seeded only an owned test Desktop
directory, disabled window/image/avatar access and used deterministic specialist reasoning.
Prompt: `Sora, please open the project notes and show me the latest result`.
The answer identified `project-notes.txt`, reported `VOICE PARITY CHECK PASSED. No desktop effects
were requested.` and included a `read_file: filesystem, ok` source timestamp. Repeating the exact
event returned duplicate/no playback and left exactly two canonical messages. Runtime/model cleanup
completed; an unrelated pre-existing Hermes llama-server process was left untouched.

## Installed local speech component probes

No production dependency or settings changes were made by these probes. Existing cached packages
were used in isolated `uv run --offline --isolated --python 3.12` environments.

- faster-whisper **1.2.1**, local base.en snapshot under `.local/p14-voice-benchmark/models/stt/`,
  `local_files_only=True`: transcribed `.local/p14-voice-benchmark/corpus/sapi-1.wav` as
  `Sora, please open the project notes and show me the latest result`.
- kokoro-onnx **0.6.1**, `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin`: synthesized
  `SORA local voice is ready.` with `af_heart`, `en-us`, speed 1, yielding **42,496 samples**,
  **24,000 Hz**, peak approximately **0.4101**. soundfile version **0.14.0** imported successfully.
- sounddevice **0.5.5** enumerated the Windows input/output inventory, including the default
  PlayStation Link microphone and speakers. This did not open a microphone or speaker stream.

These establish usable existing STT/TTS assets and enumeration support. They are separate component
checks, not a complete audio pipeline, noisy-room benchmark or owner confirmation of device choice.
The synthetic STT phrase was reused as the live Core test input; PCM was not carried through Core.

## Reproduction

```powershell
./scripts/verify.ps1
uv run --locked pytest tests/voice/test_companion_parity.py tests/voice/test_sessions.py -q
dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore
$env:SORA_TEST_VOICE_MODEL_CONFIG = 'C:/Users/oscar/Desktop/SORA/.local/native-read-qa-20261002/llama.json'
uv run --locked pytest tests/voice/test_companion_parity.py::test_voice_local_model_discovers_and_reads_note -q -s
Remove-Item Env:SORA_TEST_VOICE_MODEL_CONFIG
```

The model test is deliberately opt-in and uses already-present weights. Do not treat its disabled
default as a failing test or enable paid/cloud providers to replace the specified local model.

## Still open / next implementation

Reuse the existing streaming voice client and presentation clock with real bounded local STT/TTS
and input/output adapters. Expose press-to-talk, stop playback and truthful device state in both
Windows surfaces, with important model/device preferences in the existing JSON/Settings store.
Verify actual microphone input, audible playback, barge-in, disconnection/recovery, mouth reset,
spoken cursor timing, noisy-room/echo behavior and ordinary startup. No always-on recording is
introduced by this slice. There was no fresh Computer Use voice test during this delivery.

The broad action schema, delegation/model catalogue, avatar lifecycle and all other outstanding
requirements remain in the [active tracker](FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md).

