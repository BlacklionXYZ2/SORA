# W5 Windows voice — implementation and acceptance evidence

Implementation slice completed **2026-10-03 01:07:47 +01:00**, contributor GPT-6 Astra.
Overall W5 and frontend alignment remain **in progress**.

| Check | Evidence | Boundary |
|---|---|---|
| Installed STT/TTS | Actual Whisper recognized the SAPI phrase about project notes; Kokoro generated 24 kHz PCM | Synthetic utterance, not owner speech |
| Actual worker | Loaded installed assets, opened Core session, reached Ready | No microphone opens on Start |
| Microphone | 0.3-second default-device capture yielded PCM, stream closed, bytes discarded | No transcription/history/audio file or intelligibility assessment |
| Speaker | Actual Kokoro “SORA local voice is ready.” written to default output; finish/close succeeded | API success, not confirmation that owner heard it |
| Revocation cleanup | Actual worker kernel handle signalled after static voice OFF | Actual child and venv launcher checked |
| Stalled cleanup | Core kernel-handle and private-pipe EOF tests exit a child sleeping on its main thread | Lifecycle test, no live mic in deliberate stall |
| Startup race | Delayed process creation revoked before initialization; new process stopped | Deterministic concurrency test |
| Full-app GUI | Voice entry, Loading/Ready, devices, Stop, Close and wrapped layout | Isolated offline model; no spoken GUI turn |
| Settings | V5 backup/migration, v6 persistence/live callback, picker schema | GUI recheck failed on input geometry, remains open |
| Regression | 571 Python passed / 23 skipped; 8 PWA; 37 C#; zero-warning builds | Skips not treated as passed |

## Commands and final results

```powershell
$env:UV_PROJECT_ENVIRONMENT='.local/frontend-verify-20261003'
./scripts/verify.ps1

# Hardware opt-in opens the mic briefly and plays a benign static phrase
$env:SORA_TEST_LOCAL_VOICE='1'
$env:SORA_TEST_LOCAL_AUDIO='1'
.local/voice-runtime/Scripts/python.exe -m pytest tests/voice/test_windows_voice.py -q

dotnet build clients/desktop_app/desktop_app.csproj --verbosity quiet
dotnet build clients/desktop_widget/desktop_widget.csproj --verbosity quiet
dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet
```

Final standard run: **571 passed, 23 skipped in 73.81s**; final voice run:
**13 passed in 11.29s**. Ruff, mypy (235 files), schema freshness and compileall passed.

GUI profile `.local/voice-gui-qa-20261003`, loopback port 18788, paused perception,
file/desktop/delegation/avatar access disabled. GUI explicitly displayed **Offline test model**.
Owner Core was not stopped/relaunched. QA processes closed; subsequent read-only checks
found no 18788 listener or voice worker. Existing weights reused; dependency installation
did download software packages. Final text is ordinary history during actual voice use;
the capture probe sent no transcript and persisted no audio.

## Failures repaired

1. Worker Loading stalled for over 90 seconds. Private bounded diagnostics/traceback located
   first NumPy native initialization in the loading thread. Main-thread imports fixed startup.
2. SAPI fixture was 22.05 kHz rather than 16 kHz. The test resamples it without relaxing
   production PCM validation.
3. Instructions/device keys clipped. Shared form wraps text and scrolls device names;
   repaired full-app voice view inspected after rebuild.
4. Venv launcher termination alone was insufficient lifetime evidence. Closing pipes and
   a kernel-handle/pipe watchdog stop the actual process, including native stalls. Tests
   hold kernel handles before exit so PID reuse cannot falsely pass.
5. Static revocation could overtake subprocess creation. Epoch checks now stop the newly
   returned process before initialization data is sent.
6. Near-silence previously went to inference and confidence was fixed. Silence is rejected,
   no-speech segments excluded, confidence derived from word probabilities. This remains
   a heuristic rather than a calibrated recognition-quality claim.

## Remaining acceptance / next implementation

- Connect PCM playback presentation to the 3D mouth sink and verify reset on Stop, close,
  worker death and device loss. The real worker currently uses the null sink.
- Human-spoken GUI read/action turn with configured local model, audible answer, transcript
  inspection and barge-in. Earlier Core-only real-model evidence does not close this gate.
- Actual unplug/reconnect and loss reporting/recovery with no stale audio.
- Compact-menu entry, GUI Settings picker/save/live restart, keyboard/mouse timing,
  mixed DPI and ordinary one-script startup/packaging.
- Product loading watchdog/error polish and device-dropdown UX. Close audio terminates
  the worker, but a user-facing loading timeout is not implemented.

[Runbook](../runbooks/SORA_LOCAL_VOICE.md) and
[changelog](../../changelog/2026-10-03T010747+0100_W5-WINDOWS-VOICE-BRIDGE_GPT-6.1-Sol.md).
