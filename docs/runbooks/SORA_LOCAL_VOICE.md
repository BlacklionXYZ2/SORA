# Local Windows voice

The full Windows app has a **Voice…** button in Chat. The compact widget has
**Local voice…** in its menu. Both open the same Core-owned press-to-talk window.
This is not the PWA's browser speech backend and does not enable always-on recording.

## First setup

From the SORA project, run `./scripts/setup-local-voice.ps1` once, or pass `-SetupVoice`
to `./Start-SORA.ps1` or `./scripts/start-full-sora.ps1`. This installs locked Python
speech dependencies into `.local/voice-runtime`, separately from Core's environment.
It can download software packages, but it does **not** download speech weights.
Normal launches do not install optional speech dependencies automatically.

Restart Core and the Windows client normally to load this implementation. An already
running older Core/client does not gain the new controls from editing source files.

In **Settings → Voice**, select the local faster-whisper model directory, Kokoro
ONNX model, and Kokoro voice-bank file. The file/folder pickers are part of Settings;
no manual JSON edit is required. Blank fields reuse the project's existing P14 voice
benchmark assets only when an unambiguous complete installation exists. Otherwise
Start voice reports the missing asset; it does not silently fetch weights or use a cloud service.

Blank Python interpreter selects `.local/voice-runtime/Scripts/python.exe` when
available, otherwise Core's interpreter. Use an explicit local interpreter only if
it has the required optional dependencies installed.

## Using it

1. Open Voice… and click **Start voice**. Loading checks devices and loads local models;
   it does not open the microphone. Wait for **Ready**.
2. Hold **Hold to talk**, speak, then release to submit. Space works while that button
   has focus. Capture ends at the configured limit (30 seconds by default), even if
   the button remains held. The microphone closes before transcription starts.
3. SORA transcribes locally, uses the existing shared companion dialogue path, and
   speaks the answer locally. The window shows Recording, Transcribing, Thinking,
   Speaking and Ready rather than claiming every request immediately succeeded.
4. Hold again to interrupt and begin another utterance. **Stop response** stops current
   local capture/output and requests cancellation. **Close audio**, or closing this
   window, stops the shared local audio worker for every SORA window connected to Core.

Windows defaults are used when device keys are blank. After Start voice, the window
lists current host-API/device keys. Copy a key into the microphone or speaker field
in Settings to select a particular device. Missing/ambiguous configured devices fail
visibly instead of switching to another device. Long device names scroll horizontally.
Device selection is currently a key field, not a dropdown.

Settings also expose voice name (default `af_heart`), speed (0.5–2), and capture limit
(2–60 seconds). Save applies these preferences live by stopping the old voice worker;
click Start voice again to load the new selection. No model reload is needed for these
voice fields. Voice preferences live in shared settings v6; v5 migration backs up the
original file and preserves previous preferences.

PCM stays in worker memory. It is not sent in Core JSON, stored in project logs, or
persisted as an audio recording. Final recognized text and SORA's response are ordinary
conversation records. Technical read-evidence footers remain in history but are not
read aloud. Private pipe messages and Core credentials never enter the settings store.

## Verification boundary

Automated tests cover actual installed Whisper/Kokoro adapters, short microphone capture
with immediate discard, default-speaker playback, worker startup/reaping, parent-death
binding and revocation during launch. Full-app GUI Start/Ready/Stop/Close and the wrapped
voice layout were reviewed with Computer Use in an isolated offline-model QA profile.

On 2026-10-03 the Settings GUI recheck exposed and repaired Windows v6 recognition: without
the repair, the client displayed the old settings page. Rebuild the Windows client to obtain
all new controls. Section navigation, a GUI Voice speed Save and restart persistence passed.
Compact-menu Start/Ready/Close with real child-worker reaping and root automatic client launch
also passed, without opening the microphone. QA restarts were forced, not graceful shutdown.

Still required: a human-spoken GUI prompt with the configured dialogue model and audible
answer/mouth movement, barge-in while speaking, real device unplug/reconnect, mixed-DPI layouts
and graceful shutdown acceptance. See [latest startup/GUI evidence](../verification/W1_W5_STARTUP_SETTINGS_GUI_GPT-6-Astra_2026-10-03.md).

The real worker now sends bounded PCM-amplitude presentation samples to the connected
Unity companion. This is a transient output channel, not a model-callable animation tool;
it carries no PCM or transcript and never replays after reconnect. The avatar must be
running, loaded and enabled. A short watchdog closes the mouth during missing frames.
Reset is connected for completion, interruption, device-loss events, close and disconnect.
Actual packaged sample-VRM/speaker checks passed, including zero applied expression weights
after reset. Device loss was simulated, not a physical unplug. This is basic amplitude-driven
mouth movement, not phoneme/viseme animation or a measured audiovisual synchronization claim.
W5 remains in progress until the real-user GUI/device and ordinary-startup gates above pass.
