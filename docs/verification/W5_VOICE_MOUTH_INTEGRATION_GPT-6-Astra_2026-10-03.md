# W5 — PCM presentation to packaged VRM

Implementation slice completed **2026-10-03 01:34:44 +01:00**, attribution GPT-6 Astra.
W5 and the frontend alignment goal remain **in progress**.

## Path and scope

Actual Kokoro PCM → existing local amplitude clock → `PipeLipSyncSink` metadata → private
Core-owned worker pipe → transient bounded relay → authenticated renderer WebSocket →
Unity main-thread controller → VRM mouth expression. PCM remains local; speech text is not
included in the renderer channel. Frames are not commands, task results, durable records or
model-callable tools. There is no incoming API for model-generated mouth samples.

Tests separately exercise the pipe sink, bounded relay/overflow, metadata parser/duplicates,
epoch restart, clock continuity, timeout mouth closure and cancelled native-write ownership.
Renderer connection and static access checks remain in force; voice OFF can still deliver
a reset, while new frames are suppressed. Reconnect never hydrates old audio presentation.

## Final verification

| Check | Result |
|---|---|
| Standard Python suite | 575 passed / 24 opt-in skipped, 76.94s |
| PWA | 8 passed |
| Ruff / mypy / contracts / compileall | Passed; 238 mypy source files |
| C# transport/client tests | 40 passed |
| Both Windows clients | Zero-warning/error builds |
| Unity PlayMode and packaged build | 61/61 passed; player rebuilt after final Unity edits |
| Focused client/relay/write-ownership tests | 24 passed |
| Packaged VRM/speaker integration after native repair | Two consecutive passes: 27.86s and 28.48s |

The packaged test uses synthetic finalized “Hello SORA.” text and an offline dialogue
provider, actual Kokoro and default PortAudio speaker, and a loaded packaged sample VRM.
It verifies both the requested Aa weight and UniVRM's **actually applied** expression weight.
Completion, interruption, simulated device loss and session close each return these to zero.

Final artifacts:

- `.local/w5-voice-mouth-evidence/3454b46be2c3422592e1f450f805c1e6/voice-frames.json`
- `.local/w5-voice-mouth-evidence/ae3d553058dd4d39aa5999c6e4c29441/voice-frames.json`
- Same directories contain bounded test-player logs.
- `.local/p09-unity-evidence/playmode-results.xml` reports 61 passed / 0 failed.

Final integration initial playback: **92 evidence records**, peak weight **0.3804052**.
Final record at `2026-10-03T00:33:20.2781553Z`: no active playback, output epoch -1,
mouth/desired/applied weights **0**, emotion neutral, reset reason Disconnected.
Read-only post-test checks found no packaged SORA player or voice worker. Owner Core was
not stopped or restarted. Tests did not open the microphone or read owner files.

## Failures investigated

- C#/Unity compilation errors during wiring were corrected before the final rebuild.
- Repeated client close attempted a closed Core session. Close now remains idempotent
  while still resetting local output; the packaged cleanup/repeat test passed afterward.
- A repeat integration run crashed with a Windows native audio access violation during
  interruption. The adapter allowed a cancelled background native write to overlap stream
  closure. Serialized native operations and a blocking-write ownership test address this;
  two subsequent complete packaged runs passed. This is an observed repaired failure, not
  a claim that every possible device/driver hang has been tested.
- Evidence now samples two late frames after changes, rather than counting only a setter
  as proof that the runtime applied the reset.

## Reproduction

```powershell
./scripts/build-embodiment.ps1
$env:SORA_TEST_UNITY_VOICE='1'
.local/voice-runtime/Scripts/python.exe -m pytest tests/voice/test_unity_voice_bridge.py -q -s
# This speaks a benign offline response through the default speaker; no mic capture.

$env:UV_PROJECT_ENVIRONMENT='.local/frontend-verify-20261003'
./scripts/verify.ps1
```

## Remaining gates

Human-spoken GUI interaction through the real configured LLM, actual child-worker audio/
presentation end-to-end, physical unplug/reconnect, ordinary launch/restart, custom avatar,
Settings/compact GUI acceptance, mixed DPI and subjective audiovisual quality. The integration
test forwards the pipe sink's output in-process; it does not prove those broader requirements.
Device loss is simulated. Basic amplitude-driven movement is not phoneme animation or a
measured synchronization result. No new Computer Use GUI review occurred in this slice;
the preceding voice-window GUI evidence remains separate.

[Changelog](../../changelog/2026-10-03T013444+0100_W5-VOICE-MOUTH-INTEGRATION_GPT-6.1-Sol.md).
