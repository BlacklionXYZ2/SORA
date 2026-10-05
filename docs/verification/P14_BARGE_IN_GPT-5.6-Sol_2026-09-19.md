# P14.3 barge-in — GPT-5.6 Sol

Status: **complete 2026-09-19 11:23:36 +01:00**.

P14.3 gives voice interruption an explicit lifecycle instead of treating every request to silence
SORA as cancellation. The implementation separates acoustic output, response generation and durable
dialogue finalization so each can stop at the correct boundary.

## Interruption semantics

| Mode | Local speaker and lip-sync seam | Queued/playing Core output | Active dialogue generation | Durable result |
|---|---|---|---|---|
| `barge_in` | Stop immediately | Invalidated | Cooperatively cancelled | None when cancelled before finalization |
| `stop_speaking` | Stop immediately | Invalidated | Continues | User/assistant turn commits; no playback |
| `cancel_response` | Stop immediately | Invalidated | Cooperatively cancelled | None when cancelled before finalization |

The modes are an enum rather than a caller-supplied combination of booleans. This prevents a generic
“stop” action from silently expanding into reasoning cancellation.

## Core generation and output lifecycle

- A final transcript creates a unique named generation task associated with its authenticated voice
  session. The session snapshot exposes only the opaque generation ID and cancellation/output state.
- Every effective interruption advances a monotonic `output_epoch`, clears the active playback and
  suppresses output from a still-running generation. Playback commands carry the epoch.
- A barge-in or explicit cancel marks cancellation before cancelling the provider task. The awaiting
  transcript resolves as `interrupted`, with no durable messages or playback when cancellation occurs
  before the provider completes.
- Stop-speaking never cancels the generation. The response finishes, the user and assistant messages
  commit atomically, and the changed output epoch prevents a playback command.
- Once provider generation has completed, the repository commit runs behind a protected atomic
  boundary. An interruption during that short boundary preserves the complete canonical turn but
  suppresses output. SORA does not claim rollback of work that has already crossed finalization.
- Closing the session or runtime requests cancellation of active generation and clears volatile voice
  state.

## Responsive client behavior

P14.2 waited for TTS/playback inside frame processing. P14.3 moves it to a background task so the
capture loop can continue observing speech.

- A new VAD speech onset sees the active response and automatically calls barge-in before forwarding
  the new transcript.
- Speaker abortion and lip-sync reset happen locally before the interruption request waits on Core,
  minimizing acoustic overlap.
- A stale playback command whose epoch does not match the current session snapshot is ignored.
- TTS cancellation discards later chunks, aborts the sink and resets presentation. Completion,
  failure, output-device loss and close also reset the same seam.
- `stop_speaking(cancel_generation=False)` is the safe default. The caller must pass the explicit
  cancellation form to abandon reasoning.

P14.3 defines only the reset boundary for lip sync. It does not generate visemes or animate a mouth;
that timing implementation is P14.4.

## Authorization, ordering and idempotency

- `POST /api/v1/voice/sessions/{session_id}/interrupt` is authenticated like the other voice routes.
- Core rechecks the persisted exact `voice.session:<session>:input:<device>:output:<device>` grant
  before mutating interruption state. Revocation returns 403 and cannot silence or cancel another
  session.
- Interruption event IDs are bounded and idempotent. Reusing an ID with changed input fails closed;
  exact delivery replay returns `duplicate` without advancing the epoch or issuing cancellation
  twice.
- Session/device ownership remains enforced, and interruption timestamps use the same future/stale
  bounds as transcript, device and playback events.

## Acceptance evidence

The machine-readable record is
[`p14-barge-in/acceptance.json`](p14-barge-in/acceptance.json). Deterministic fixtures prove:

- automatic new speech cancels one blocked provider generation;
- the cancelled response creates zero messages and zero playback commands;
- stop-speaking allows one provider completion and one atomic user/assistant turn but creates zero
  playback commands;
- queued output is removed and cannot accept stale playback events;
- client TTS produces one initial chunk, is aborted, and never writes its later stale chunk;
- the presentation reset seam is invoked; and
- grant revocation prevents interruption.

## Limitations

- Provider generation cancellation is cooperative. The asynchronous dialogue provider must honour
  task cancellation; a provider that deliberately swallows cancellation violates the provider
  contract. Output epochs still prevent such a provider from producing audible output.
- This stage uses deterministic adapters and does not measure physical microphone-to-silence latency
  or acoustic echo on real speakers.
- The lip-sync integration in P14.3 is a reset protocol only. Audio-clock/viseme or validated
  amplitude-driven presentation is P14.4.
- Cross-device/mobile interruption and delayed spoken-reference intent remain P14.5/P15 concerns.

## Verification

| Gate | Result |
|---|---|
| Voice suite | 18 passed |
| Focused voice + persistence + API | 22 passed |
| Repository | 320 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed; strict mypy passed across 171 source files; schemas fresh; compileall passed |

Roadmap after P14.3: 76/91 checklist items (83.5%). P14.4 mouth/emotion synchronization is next. No
commit, tag or staging operation was performed.
