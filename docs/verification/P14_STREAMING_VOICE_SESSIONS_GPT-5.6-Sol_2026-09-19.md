# P14.2 streaming voice sessions — GPT-5.6 Sol

Status: **complete 2026-09-19 11:07:22 +01:00**.

P14.2 establishes an authenticated semantic streaming path from a local voice client through SORA
Core and back to local playback. It deliberately keeps raw audio and inference buffers outside Core:
the shared boundary carries transcripts, device state and playback state only.

## Verified flow

1. A client obtains microphone frames locally as `AudioFrame` values.
2. Client-local VAD and STT adapters turn those frames into partial or final
   `VoiceTranscriptEvent` values.
3. Core accepts partial text into bounded volatile session memory. Partials do not invoke dialogue,
   create messages or enter SQLite.
4. A final utterance is serialized, resolved through a durable owner/device/session/utterance key,
   sent to the dialogue provider once, and committed as one user message plus one assistant reply in
   the same database transaction as its receipt.
5. A newly created turn may return one semantic `VoicePlaybackCommand`. It expires after 30 seconds;
   reconnect/restart duplicates return the durable turn without a new command.
6. Client-local TTS produces audio chunks for a local playback sink and reports STARTED, COMPLETED or
   FAILED state back to Core.

The acceptance fixture executes this complete route using deterministic VAD/STT/TTS/playback
adapters. Its transport asserts that no PCM or audio field crosses into Core.

## Authorization and privacy

- Session creation requires a persisted reusable `VOICE_SESSION` grant over the exact resource
  `voice.session:<session>:input:<input-device>:output:<output-device>`.
- The authenticated device must own the session. Core rechecks the grant before each transcript,
  device or playback update; caller `authorized_by` values are not accepted.
- Public voice models are strict and contain no raw audio, sample, grant or authorization fields.
- Partial transcript text is bounded and volatile. The acceptance test verifies a unique partial
  marker is absent from the SQLite database bytes and that dialogue is not called.
- Closing a session or shutting down the runtime clears the volatile coordinator state.

## Exactly-once finalization

The repository migration adds a `voice_utterances` receipt keyed by owner, device, session and
utterance. The receipt contains a final-transcript SHA-256 and the two canonical message references.
Creation of the user message, assistant reply and receipt is one transaction.

- Two concurrent deliveries of the same final event produce one FINALIZED result and one DUPLICATE
  result, one dialogue call, one user row, one assistant row and one playback command.
- A different delivery event after runtime restart resolves to the same receipt without calling the
  dialogue provider or creating playback.
- Reusing the utterance key with different final text fails closed on the transcript digest.
- A replay of the exact event ID is idempotent and cannot repeat playback.

The plan's singular-message acceptance is interpreted at the user-input boundary: one finalized
speech utterance creates exactly one durable user message. SORA's normal dialogue contract also
creates exactly one durable assistant reply.

## Echo and device recovery

- Queuing a response is not treated as audible output. Echo comparison begins only after the client
  reports playback STARTED.
- A normalized high-similarity final transcript matching active playback is suppressed without a
  provider call or durable message.
- Input loss clears the active partial and rejects transcription until recovery advances the input
  generation exactly once. Old-generation events are rejected.
- Output loss abandons active playback. Recovery advances the output generation and deliberately does
  not reconstruct the old command, so stale audio cannot play later.
- Playback events must target the exact output device, current generation and active playback, and
  must advance a strict sequence. COMPLETED is legal only after STARTED; FAILED may terminate queued
  or started output.

## API and schemas

Authenticated routes and matching local SDK calls cover:

- `POST /api/v1/voice/sessions`
- `GET /api/v1/voice/sessions/{session_id}`
- `POST /api/v1/voice/sessions/{session_id}/transcript`
- `POST /api/v1/voice/sessions/{session_id}/device`
- `POST /api/v1/voice/sessions/{session_id}/playback`
- `POST /api/v1/voice/sessions/{session_id}/close`

Seven generated schemas publish the session-start, session-snapshot, transcript, device, playback
event, playback-command and turn-result contracts. The existing capability schemas include
`voice.session` as an operation.

## Acceptance evidence

The machine-readable record is
[`p14-voice-session/acceptance.json`](p14-voice-session/acceptance.json). It records:

- exactly one durable user message and one assistant reply for one final utterance;
- one provider call and one playback command under concurrent delivery;
- zero durable messages and zero provider calls for partials;
- zero duplicate messages or playback commands after restart;
- zero turns created from an active-playback echo;
- no stale audio after output-device recovery; and
- no raw PCM on the Core transport.

## Limitations and next gate

- The verified end-to-end client uses deterministic fake VAD/STT/TTS/playback adapters. P14.2 did not
  open a live microphone or speaker, exercise acoustic echo cancellation, or measure physical-device
  latency/noise quality.
- P14.1 separately measured Silero VAD, faster-whisper and Kokoro on the reference desktop. Wiring
  those engines into a distributable hardware client remains client/release work rather than a Core
  dependency.
- P14.2 does not stop a currently generating response or interrupt queued/playing audio on new speech.
  Those barge-in semantics are P14.3.
- Mouth animation and audio-clock/viseme synchronization remain P14.4.

## Verification

| Gate | Result |
|---|---|
| Voice suite | 13 passed |
| Focused voice + persistence + API | 17 passed |
| Repository | 315 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed; strict mypy passed across 171 source files; schemas fresh; compileall passed |

Roadmap after P14.2: 75/91 checklist items (82.4%). P14.3 barge-in is next. No commit, tag or staging
operation was performed.
