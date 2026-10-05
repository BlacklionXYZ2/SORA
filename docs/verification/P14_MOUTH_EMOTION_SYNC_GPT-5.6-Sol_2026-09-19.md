# P14.4 mouth and emotion synchronization — GPT-5.6 Sol

Status: **complete 2026-09-19 12:14:23 +01:00**.

P14.4 synchronizes SORA's presentation with synthesized audio while keeping animation authority in
the local client. The language model supplies text and, at most, one coarse utterance emotion. Mouth
movement is derived from PCM and cannot be supplied as a Core or model frame command.

## Local audio clock and amplitude fallback

`SynthesizedAudioChunk` is a client-local type containing an exact sequence, non-empty complete
signed-16 little-endian PCM frames, sample rate and one/two-channel declaration. It rejects malformed
sample widths, unsupported channel counts, out-of-range rates and sequences.

`VoicePresentationClock` binds those chunks to the active playback command and derives:

- cumulative audio position from exact sample-frame count;
- chunk duration from sample rate rather than wall-clock guesses;
- normalized RMS amplitude from every signed-16 sample;
- a 0.012 noise floor and bounded 3.5 gain;
- faster 0.72 attack and slower 0.38 release smoothing; and
- bounded mouth openness in `[0, 1]`.

The deterministic fixture verifies zero RMS for silence, 0.5 RMS for known half-scale PCM, exact
10-ms positions for 240 samples at 24 kHz, rising bounded mouth output and strict sequence handling.

## Identity and stale-frame safety

Every local presentation frame carries:

- the server-created playback ID;
- the current output epoch from P14.3;
- an exact zero-based audio-chunk sequence;
- monotonic position and duration; and
- the playback command's coarse emotion.

Both the Python clock and Unity controller require the complete active identity. Reset removes that
identity. A late old-playback frame is rejected even when a new turn uses the same output epoch; an
older epoch, skipped/repeated sequence, backwards clock, mismatched emotion or old reset is also
rejected without changing the mouth.

## Reset lifecycle

The streaming client resets presentation on:

- normal playback completion;
- output-only pause;
- barge-in or explicit response interruption;
- output-device loss;
- session disconnect/close; and
- synthesis, playback or transport failure.

Local speaker cancellation and presentation reset remain coupled. The sink receives the affected
playback identity and reset reason; forced disconnect/interrupt reset is still issued when no local
task is visible, preventing a remote avatar from remaining stuck in a speaking pose.

## Coarse emotion and Unity VRM presentation

`VoicePlaybackCommand` now contains one enum-valued `neutral`, `warm`, `cheerful`, `concerned` or
`focused` emotion and defaults to SORA's warm presentation. It is utterance-level metadata, not an
animation curve.

Unity's `AvatarVoicePresentationController` is configured against the loaded `Vrm10Instance` and:

- applies mouth openness to UniVRM `ExpressionKey.Aa`;
- maps cheerful to a bounded happy weight, warm to relaxed, concerned to sad and focused to a small
  neutral weight;
- zeros mouth and emotion on every reset;
- validates playback identity, epoch, sequence, position, duration, amplitude and emotion; and
- clears itself when disabled or disconnected.

The controller is not a Core command handler. There is no `voice_frame`, `mouth`, or `viseme`
`EmbodimentCommandDto` verb. The Python `VoicePresentationFrame` is also absent from the public
contract registry. Generated playback schemas expose only the coarse emotion and playback identity.

## Verification evidence

Actual Unity 6.0.6 PlayMode execution completed **55/55** tests. The new P14.4 fixture contributed six
passing cases covering:

- ordered audio-clock mouth and emotion application;
- amplitude bounds;
- stale playback rejection after reset and replacement;
- independent pause, interruption and disconnect reset cases; and
- invalid sequence/backwards-clock rejection.

The machine-readable summary is
[`p14-mouth-emotion/acceptance.json`](p14-mouth-emotion/acceptance.json). Local raw Unity evidence is
retained under `.local/p09-unity-evidence/playmode-results.xml` and reports 55 passed, zero failed and
zero skipped.

## Limitations

- No physical speaker/camera measurement was performed, so this stage does not claim observed
  audiovisual offset, microphone echo quality or subjective animation naturalness.
- The initial validated fallback drives one `aa` shape from amplitude. A TTS adapter with trusted
  phoneme timings can provide richer visemes later while retaining the same playback identity and
  reset rules.
- The current default dialogue path supplies `warm`; richer coarse emotion selection still requires
  a dialogue-provider result contract rather than parsing or obeying generated animation frames.
- A deployable cross-process client transport is P15 work. P14.4 validates the local sink interface,
  deterministic voice client and actual Unity presentation controller independently.

## Gates

| Gate | Result |
|---|---|
| Voice suite | 21 passed |
| Focused voice + persistence + API | 25 passed |
| Unity 6.0.6 PlayMode | 55 passed, including P14.4 6/6 |
| Portable C# | 22 passed |
| Embodiment verification | 43 passed, 3 explicit packaged/native skips |
| Repository | 323 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed; strict mypy passed across 172 source files; schemas fresh; compileall passed |

Roadmap after P14.4: 77/91 checklist items (84.6%). P14.5 speech-reference and interruption-intent
alignment is next. No commit, tag or staging operation was performed.
