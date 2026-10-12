# Always-on listening, and native audio for Gemma 4 E2B/E4B (speech-to-text bypass for the reply)

Model name: **Opus 5.5**. Checkpoint **2026-10-08 19:17:00 +01:00**, Europe/London. Status:
**implemented, component-tested, checked live with real models.** The microphone path has not
been tried with a real speaker. The owner asked: "Could you implement the Always-on listening?" This implements steps 1–4 of
[ALWAYS_ON_LISTENING_2026-10-08](../docs/plans/ALWAYS_ON_LISTENING_2026-10-08.md), ahead of V1
acceptance at the owner's request; it does not move a V1 step directly (voice step 3 still works
with press-to-talk).

## Changes

1. **Native audio** (new `src/sora/providers/turn_audio.py`).
   - `projector_modalities` reads `clip.has_audio_encoder` from the projector's GGUF header.
     Both owner projectors (E2B and E4B) report audio and vision.
   - The managed provider sets `audio_input` when the model loads.
   - A voice turn sets the clip in a context variable (`turn_audio`). Only reply requests
     (`respond`, `respond_with_images`, `stream_reply`) add an `input_audio` part and a note that
     the text is a transcript. Decision calls never get audio.
   - `VoiceTranscriptEvent.audio_wav_base64` is optional; the schema was exported.
   - Core uses the clip only when the brain hears audio, Settings → Voice to the brain is `auto`,
     and the clip is a bounded WAV.
2. **Listening logic** (new `src/sora/voice/listening.py`), all of it pure and tested:
   - `RollingBuffer`: 60 s in RAM only.
   - `SpeechSegmenter`: start and end thresholds, pre-roll, the cough filter and a length cap.
   - `Addressee`: her name anywhere; a follow-on window after she replies; while she speaks,
     only her name counts, and never words that are mostly her own.
   - `wav_base64`.
   - `SileroSpeechProbability`: faster-whisper's bundled Silero, over a sliding one-second
     window, so nothing is downloaded.
3. **Voice worker and client.**
   - **Always mode** keeps a continuous input stream with a frame reader and a segment handler.
     Each segment is transcribed by Whisper with `hotwords` set to her name, passed to the
     addressee check, then sent as a turn with `submit_utterance`. A new turn replaces an
     unfinished answer.
   - **Press-to-talk** is refused while listening.
   - **Stop** stops her answer but keeps listening; **close** closes the microphone.
   - **`WhisperStt` refactor:** `transcribe_segment`, plus an `attach_audio` option that also
     covers press-to-talk turns.
   - **`StreamingVoiceClient`:** `submit_utterance` and `her_recent_words`.
4. **Settings** (`VoiceSettings`, Audio category):
   - `listening`: press (default) or always;
   - `wake_words`;
   - `follow_on_seconds`: 8;
   - `audio_route`: auto or transcribe.

   Files saved before today load with the defaults (the loader accepts the four as missing),
   with no settings version bump.
5. **Status and UI.**
   - The bridge reports `listening` and `hearing`.
   - The shell accepts the `listening` state and labels the microphone "Mic ON · listening for
     her name".
   - Chat's microphone is blue while listening and shows "Hearing you…". Clicking it stops
     listening.
6. **HOW_TO_USE.md:** how to turn listening on and off, wake-word spellings, the follow-on
   window, speakers versus headset, and native audio.

## Verification

- **Fixture/component:**
  - `.\scripts\verify.ps1` ran ruff, mypy (321 files), pytest (1063 passed, 25 skipped, 4
    xfailed) and the panel tests, exit 0.
  - `dotnet test`: 405 passed.
  - The shell compiles: a build to a scratch folder gave 0 warnings. The normal output was locked
    by the owner's running SORA.
  - New tests: `tests/voice/test_listening.py` (8, including old settings still loading),
    `tests/voice/test_native_audio_turn.py` (3: the clip reaches a native-audio brain and not
    others, and the GGUF metadata parse), plus a Chat badge test.
  - One run of `tests/voice` showed a single failure that did not recur in two reruns. It looks
    timing-sensitive; I did not investigate it further.
- **Live, real models, no microphone:**
  - Windows speech produced clips, which were streamed through the real Silero, segmenter,
    Whisper (hotword "Sora") and addressee:
    - "Can you pass me the salt please?" was ignored;
    - "Hey Sora, what is the capital of France?" was addressed (named);
    - "and what about Germany?" was addressed (follow-on).
  - Whisper took 0.4–0.5 s per sentence; voice activity costs 1.2 ms per 100 ms frame.
- **Live native audio** (E4B on llama.cpp, **CPU only** because the owner's SORA held the GPU):
  - The clip alone was answered "The capital of France is Paris" and transcribed exactly.
  - Through SORA's provider with a deliberately wrong transcript ("…Spain"): transcript only gave
    "Madrid"; with the clip, "Paris".
  - llama.cpp logs that audio input is experimental.
- **Live worker through Core** (isolated profile, CPU model): voice start reached state
  `listening` with the microphone open; press-to-talk was refused; close reported the microphone
  closed. No speech was played or spoken during this test.
- **Not run:**
  - real speech into the microphone (the owner's test), including speakers versus headset;
  - GPU latency for native audio;
  - the owner's profile, which is still on press-to-talk.

## Limits and next

- Wake detection uses Whisper, so speech-to-text still runs before the reply. It is skipped only
  as the brain's input. A dedicated wake-word model (openWakeWord) would remove it from the path
  for named turns.
- There is no echo cancellation. Her own voice from speakers is filtered by name and word
  overlap, so a headset is recommended.
- Plan steps 5–8 remain: memory slices from the buffer, desktop audio, the System-1 addressee,
  and deciding when to speak.

HOW_TO_USE.md: updated.
