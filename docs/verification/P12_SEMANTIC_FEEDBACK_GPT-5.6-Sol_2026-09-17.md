# P12.5 semantic feedback — GPT-5.6 Sol

Status: **complete 2026-09-17 12:06:02 +01:00**.

P12.5 reports meaningful controller transitions to Core without per-frame pose inference. Feedback is volatile, bounded, non-replayed and carried only by the currently authorized embodiment connection.

## Event sources

- Native body contact emits `poked` and `grabbed`; release emits `released`; a press/release travelling no more than six physical pixels also emits `clicked`.
- Starting P12.2 motion emits `fell`; crossing a resolved P12.4 support emits one `landed` with the support identity and bounded impact magnitude.
- Invalidating the current selected window emits one `support_removed` with a bounded reason before falling resumes.
- P11's independently verified interaction terminal maps `Completed` to `completed`; Failed, Cancelled and UnknownOutcome map to `failed`. The exact interaction instance is the terminal correlation, so one interaction cannot report competing terminal outcomes.

## Storm and replay bounds

- Unity retains at most 64 pending edge events, applies 200 ms cooldowns to ordinary physical kinds and 500 ms cooldowns to click/poke, and accepts one terminal event per correlation.
- Events older than 30 seconds are discarded rather than replayed after reconnect.
- Core independently validates the current topology revision, on-display physical position and a -5/+30-second live timestamp window.
- Core deduplicates up to 1024 event IDs, enforces one terminal per correlation, applies the same cooldown classes, accepts no more than 20 events in five seconds, retains 256 volatile events and exposes only the newest 20 in the embodiment projection.
- Feedback contains IDs, kind, time, topology, position and optional bounded magnitude/reason. It contains no credentials, desktop text, window title, frame samples or private reasoning.

## Packaged acceptance

The actual packaged avatar generated native click and drag transitions, fell and landed through P12.2/P12.4, and lost three selected supports. Core received **26 accepted events** and retained a bounded 20-event projection. Exercised kinds were `grabbed`, `released`, `clicked`, `poked`, `fell`, `landed` and `support_removed`.

`completed` and `failed` use that same authenticated WebSocket transport from the P11 terminal lifecycle. They are deterministically covered by Unity buffer and Core correlation tests; the P12.5 packaged run did not repeat the separate already-accepted P11 Pause/TYPE OS-effect demonstrations solely to manufacture both terminal outcomes.

## Verification

| Gate | Result |
|---|---|
| Unity 6000.6.0f1 PlayMode | 47/47 overall; P12.5 fixtures 2/2 plus source-edge coverage in P12.4/P12.2 fixtures |
| Packaged Core/player/native input | 1/1 passed in 95.01 seconds; 26 feedback events |
| Feedback kinds | 7 physical kinds packaged; completed/failed deterministic terminal tests |
| Portable C# / embodiment | 22/22 C#; 39 passed, 3 explicit opt-in skips |
| Repository | 277 passed, 9 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 148 source files; fresh schemas and compileall passed |

Machine-readable evidence is in [`p12-semantic-feedback/acceptance.json`](p12-semantic-feedback/acceptance.json). The public contract is [`embodiment-feedback-event.schema.json`](../../contracts/schema/v1/embodiment-feedback-event.schema.json).

This stage does not trigger dialogue or autonomous reactions itself. P13.1 owns attention policy and reaction deduplication above these already bounded physical facts.
