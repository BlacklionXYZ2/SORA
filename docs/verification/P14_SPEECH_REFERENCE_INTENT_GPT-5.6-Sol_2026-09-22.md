# P14.5 speech-reference and interruption-intent alignment — GPT-5.6 Sol

Status: **complete 2026-09-22 08:22:32 +01:00**.

P14.5 joins P14 transcript timing to P10's volatile cursor history and P03A's conversational-control
boundary. A final transcript can now identify when its deictic phrase was spoken, while the grant and
raw cursor samples remain outside the transcript payload. Spoken controls produce explicit semantic
results instead of being silently converted into dialogue or unrelated work.

## Spoken-time reference resolution

`VoiceTranscriptEvent.reference_spoken_at` is optional semantic timing from a word-timing-capable STT
adapter. When present, it must be timezone-aware and fall between speech start and speech end. The
client's `TranscriptHypothesis` carries the same optional timestamp; no raw microphone or cursor data
is added to Core contracts.

Core recognizes only bounded deictic forms that require cursor history, such as “look at this
control.” It then:

- requires an out-of-band exact `desktop.observe:attention` grant;
- asks the existing P10 `AttentionTracker` for a hover at `reference_spoken_at`;
- retains P10's topology, age, confidence and capacity checks;
- remembers the resulting scoped reference through the existing resolver; and
- supplies only the resulting reference ID/kind/label/provenance to direct dialogue context.

The delayed-transcription fixture holds the cursor around `(101, 120)` while the phrase is spoken,
moves it to approximately `(902, 699)`, and finalizes STT two seconds after phrase time. The resolved
reference is `historical-control` at the earlier position. The completion-time cursor label is absent
from dialogue context.

Missing phrase timing, missing observation authority, missing/expired buffer history or failed hover
recognition does not fall back to the current cursor. Core atomically persists the user utterance and
a local clarification asking which item was meant; it does not call the dialogue provider or make an
arbitrary reference current.

## Intent-aware interruption and task control

The deterministic classifier keeps ordinary speech as dialogue and recognizes only explicit control
forms:

| Intent | Effect |
|---|---|
| `stop_speaking` | Advances the output epoch and suppresses audio without cancelling reasoning or a background task. |
| `steer_task` | Resolves exactly one active named specialist/task and uses the existing capability-negotiated steering path. |
| `cancel_task` | Resolves exactly one active task and requests cancellation of that run. |
| `new_work` | Creates a separate task from an explicit new/separate/unrelated-work request. |
| `dialogue` | Uses the configured direct dialogue provider. |

Ambiguous steering/cancellation returns `clarification_required`; unsupported steering returns
`unsupported`; a task that is no longer cancellable returns `not_applied`. `VoiceTurnResult.control`
reports the chosen intent, status, truthful message and task ID when one was actually targeted.

At client speech onset, local playback and mouth presentation still stop immediately. The client now
waits only until its first STT hypothesis before telling Core whether this was output-only
`stop_speaking` or a full `barge_in`. This prevents the spoken command “stop speaking” from cancelling
the underlying response before its meaning is known while retaining immediate local silence.

The live in-process Core acceptance fixture used one running deterministic Hermes-backed task and
proved, in order, that speech:

1. steered that exact task and reached its provider run;
2. cancelled that same run;
3. created a different task containing only the requested work description; and
4. stopped queued TTS without cancelling the new task.

No external Hermes process, physical microphone or speaker was used. “Live” here means the real Core
scheduler, repositories, voice coordinator, routing engine and provider lifecycle were exercised
together rather than testing the classifier in isolation.

## Authority and privacy boundary

- Transcript JSON contains semantic phrase timing but no raw audio, cursor samples, grant IDs or
  caller-provided reference identity.
- The attention grant travels in a separate authenticated API header and is rechecked/consumed by the
  existing operation-authorization path.
- Reference failure clarifies; it never samples the cursor at STT completion as a fallback.
- Control classification cannot supply authority. Steering and cancellation reuse the existing task
  lifecycle and provider capability checks.
- The first implementation uses deterministic explicit-language patterns. It deliberately prefers
  dialogue or clarification over guessing at implicit control.

## Verification

| Gate | Result |
|---|---|
| Voice suite | 25 passed |
| Focused voice/reference/attention/routing/API/persistence | 66 passed |
| Repository | 327 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed; strict mypy passed across 173 source files; schemas fresh; compileall passed |
| Diff hygiene | `git diff --check` passed; existing Windows LF-to-CRLF notices only |

Machine-readable acceptance: [`p14-speech-reference-intent/acceptance.json`](p14-speech-reference-intent/acceptance.json).

## Limits

- The deterministic fixture injects phrase timing; it does not claim that the measured faster-whisper
  adapter is yet wired to emit word timestamps in a deployable client.
- No physical microphone, acoustic echo, speaker-stop latency or end-to-end first-audio measurement
  was performed in this stage.
- Intent matching covers explicit safe forms. More natural paraphrases should be added through
  evaluated fixtures without weakening ambiguous-task clarification.
- Cross-process deployable clients and remote/private access remain P15 work.

Roadmap after P14.5: **78/91 checklist items (85.7%)**. P14/G5 is complete; P15.1 is next. No commit,
tag or staging operation was performed.
