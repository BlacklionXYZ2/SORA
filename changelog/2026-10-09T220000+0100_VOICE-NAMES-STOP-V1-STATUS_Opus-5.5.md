# Spoken agent names, "stop" interrupts her, and V1 status refreshed

Model name: **Opus 5.5**. Checkpoint **2026-10-09 22:00:00 +01:00**, Europe/London. Status:
**implemented and tested with fixtures and real Whisper on synthesised speech; not tried by the
owner.** The owner asked for work on the next stage while they test later. This moves V1
acceptance steps 3 (interrupting her), 5 (spoken moves to a named window) and 6 (a spoken agent
name) forward.

## Changes

- **Names the speech recogniser expects** (new `src/sora/voice/vocabulary.py`):
  - Core gives the voice worker her agents' names, including enabled custom agents'
    nicknames (`WindowsVoiceBridge.vocabulary`, sent in the worker's `init` message);
  - the worker passes faster-whisper the first wake word plus those names as `hotwords`
    (at most 12 names and 160 characters), for both press-to-talk and always-on listening;
  - before this, only "Sora" was passed, and only for always-on listening.
- **Stopping her by voice:**
  - `voice/intents.py`: the stop phrases now include bare "stop", "Sora, stop", "quiet",
    "shh", "hush", "wait", "hold on", "enough", "that's enough", "never mind" and "shut up",
    with optional "please" and her name. The whole utterance must be the request, so "wait,
    what about…" stays conversation. "Stop it" still cancels a running task, as before;
  - `voice/listening.py`: while she speaks, a bare stop phrase now counts as addressed
    without her name. It is still ignored when its words are mostly her own speech coming
    through the speakers;
  - Core's existing stop handling silences her without a new spoken reply (an existing test
    checks that no playback is produced).
- **V1.md:** the status table (now "updated 2026-10-09") and the run instructions. Your saved
  settings already use E4B and image-on-prompt (checked from the file, read-only), so steps 3
  and 4 no longer ask you to switch them. Launch is from the Desktop shortcut.
- **HOW_TO_USE.md:** how to make her stop talking, and the expected names; "Last updated" line
  updated.
- **Tests:**
  - new `tests/voice/test_vocabulary.py` (its numpy-dependent case skips in the main
    environment);
  - new `tests/voice/test_stop_phrases.py` (21 cases, including phrases that must not stop
    her);
  - `tests/voice/test_listening.py`: a bare "stop" interrupts her; her own "stop" through the
    speakers and "stop the music" don't.

## Verification

- **Fixture/component:** ruff and strict mypy clean; pytest 1119 passed, 26 skipped,
  4 xfailed.
- **Voice environment** (`.local/voice-runtime`, which has numpy): with a fake model, both
  Whisper paths received "Sora, Claude, Cody, Hermes, Aggie".
- **Real Whisper** (faster-whisper base.en on CPU, `.local/voice-vocab-qa-2026-10-09/`):
  - 12 clips: six sentences spoken by the Windows voices Hazel and Zira, one run;
  - without the names, Zira's "walk over to the Claude window" came out as "the **cloud**
    window", the owner's exact problem. With the names it came out as "Claude";
  - the other agent names came through either way; only small casing changes appeared;
  - Hazel's "Ask Aggie" was heard as "Oscargee"/"Oscar G" both with and without the names,
    so that case isn't solved;
  - synthesised voices aren't the owner's voice, so this is indicative, not acceptance.
- **Not run:** the owner's microphone, interruption through real speakers, or the full
  always-on chain live.
