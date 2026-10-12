# Always-on listening: talk to SORA without a button, with native audio for capable brains

Prepared **2026-10-08**, Opus 5.5, from a planning conversation with the owner.

**Status, 2026-10-08 19:17 (Opus 5.5): steps 1–4 implemented** at the owner's request (ahead of
V1 acceptance): native audio verified and wired with an `audio_input` flag read from the
projector; Silero voice activity, a speech segmenter, the rolling RAM buffer, the wake word in
Whisper's transcript (biased with hotwords) and the follow-on window, in `sora.voice.listening`
and the voice worker; the Listening, wake-word, follow-on and audio-route settings; Chat's
listening state. **Not yet:** a dedicated wake-word model (so the wake check still uses Whisper,
and speech-to-text is only skipped *for the reply*, not for detection), echo cancellation (her
own voice is filtered by name and word overlap instead), memory slices (step 5), desktop audio
(step 6), the System-1 addressee (step 7) and when-to-speak (step 8). See the
[changelog](../../changelog/2026-10-08T191700+0100_ALWAYS-ON-LISTENING_Opus-5.5.md). It follows the V1 acceptance run. It supplies the audio used by the
[memory manager plan](MEMORY_MANAGER_2026-10-08.md).

## 1. Owner decisions

- The owner should not have to press a microphone button. SORA recognises she is being addressed,
  as Siri does, and eventually decides herself when to speak.
- A tiny always-on model listens for SORA being addressed (her name first, other cues later).
- **Speech-to-text is for brains without native audio input.** Gemma 4 E2B and E4B have native
  audio encoders, so for them speech goes **straight to the brain** and speech-to-text is
  bypassed.
- Desktop and microphone audio may feed memories.
- Every model is swappable.

## 2. Today (verified in source, 2026-10-08)

- Voice is press-to-talk: the Chat microphone opens a session, faster-whisper transcribes, and
  the text goes to the brain. Kokoro speaks, with mouth sync and interruption.
- The brain receives text and images only. Nothing in `providers/dialogue.py` or
  `providers/llama_server.py` sends audio.

## 3. Pipeline

```
mic ─► echo cancel ─► VAD ─► rolling buffer (RAM)
                       │
                       ▼
          addressed to SORA? (wake word → follow-on window → System-1 addressee)
                       │ yes
                       ▼
     brain has native audio?  ── yes ─► audio clip straight to the brain (+ transcript, §5)
                       │ no
                       ▼
               speech-to-text ─► text to the brain
```

1. **Echo cancellation:** so her own speech from the speakers is not heard as the owner's.
   Windows' communications processing or a WebRTC-style canceller. Kokoro's output is known, so it
   can also be subtracted.
2. **Voice activity detection:** a tiny model (for example Silero VAD, about 2 MB on the CPU)
   always on, marking speech segments.
3. **Rolling buffer:** the last ~60 s of microphone audio (optionally desktop audio via WASAPI
   loopback), in RAM only. Nothing reaches disk unless a memory takes a slice of it.
4. **Addressed to SORA?**, in stages:
   - (a) **wake word** "SORA" (a small open keyword model such as openWakeWord, trainable on a
     custom name);
   - (b) a **follow-on window**: after she replies, speech within a few seconds counts as
     addressed without the name;
   - (c) later, a **System-1 addressee classifier**: speech plus context (the owner looking at her
     avatar or Chat, a question pending, a recent exchange) → addressed or not. Laya-class, and
     trained from owner corrections ("I wasn't talking to you").
5. **To the brain:**
   - **Native audio** (brain slot declares `audio_input`; Gemma 4 E2B and E4B): the segment's audio
     goes into the brain's request with the usual screen images. Speech-to-text is skipped on the
     reply's critical path, which removes a step and keeps tone and non-speech sound.
   - **Without native audio** (for example a Qwen or an external server without audio): speech-to-text,
     then text, as today.
6. **Deciding when to speak:** a later System-1 decision. It also covers interjecting unprompted,
   which is "proactivity" in VISION.md.

## 4. Native audio: things to verify first

- **The model:** that the Gemma 4 E2B and E4B GGUF exports used here include the **audio
  encoder** in their projector (`mmproj`). The current `mmproj-F16.gguf` may be vision-only; a
  separate or combined projector may be needed.
- **The server:** that the pinned llama.cpp `llama-server` accepts audio input (for example
  `input_audio` content parts) for Gemma 4, and in which formats (WAV/PCM 16 kHz).
- **Cost:** audio token cost and latency against today's Whisper path, on this PC.
- **Fallback:** if any of these fail, the brain slot reports no `audio_input` and speech-to-text is
  used. The bypass is a capability flag, never a hard requirement.

## 5. The transcript

Chat must still show what the owner said, and memories store the owner's words. With native
audio:

- **Option A (proposed):** run speech-to-text **off the critical path**, in parallel or just after,
  only for the transcript and memory. The reply does not wait for it.
- **Option B:** ask the brain to return a transcript with its reply. That is cheaper, but it mixes
  roles, and a small model may paraphrase.

## 6. Settings

- **Listening:** off / press-to-talk (today) / always on.
- **Wake word:** on, plus sensitivity.
- **Follow-on window:** seconds.
- **Audio route:** automatic (native when the brain supports it) / always speech-to-text.
- **Microphone in memories:** on or off.
- **Desktop audio in memories:** on or off.
- **Pause:** a visible tray state while the microphone is open.

## 7. Swappable slots

| Slot | Initial | Notes |
|---|---|---|
| Voice activity | Silero VAD | any VAD |
| Wake word | openWakeWord ("SORA") | any keyword spotter |
| Addressee | rules (wake word + follow-on) → System-1 | Laya-class classifier |
| Speech-to-text | faster-whisper | used when the brain lacks `audio_input`, and for transcripts |
| Brain audio | Gemma 4 E2B/E4B native | declared by the brain slot |
| Text-to-speech | Kokoro | unchanged |

## 8. Steps

1. **Verify native audio** (§4) on E4B with llama.cpp. Measure latency against Whisper.
2. **Brain capability flag** `audio_input`; a native-audio request path with the speech-to-text
   fallback; the transcript off the critical path.
3. **Echo cancellation**, voice activity detection and the rolling buffer (microphone).
4. **Wake word and follow-on window**; the Listening setting; the tray indicator.
5. **Memory integration:** pending entries take buffer slices.
6. **Desktop audio** (WASAPI loopback) into the buffer, when enabled.
7. **System-1 addressee classifier**, trained from corrections.
8. **When to speak:** with proactivity, after V1.

## 9. Open questions

- The wake word's false-trigger rate on this PC, for example with games and videos playing. To
  be measured before always-on becomes a default.
- Whether to keep the press-to-talk button alongside always-on listening (proposal: yes).
- Buffer length, and whether desktop audio is captured continuously or only on demand.
