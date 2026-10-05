# Motion interface: semantic signals in, joint rotations out

Proposed by **Opus 5.5**, 2026-10-05, for [V1.md](../../V1.md) step 5 and the
[realignment](V1_REALIGNMENT_2026-10-05.md)'s drift item 6. **Design only: nothing here is
implemented yet.** It fixes the boundary that [VISION.md](../../VISION.md) says must exist
before the owner's learned motion model is built: "its interface must be fixed before it is
built, so it can replace the deterministic layer without changes upstream".

## The rule

Language models never drive joints. Core publishes **what SORA means** (intent, emotion,
attention, conversational state and her voice's audio envelope). A **motion layer** turns that
into movement. Today that layer is deterministic: Unity presentation states and the
`EmbodimentCommand` lifecycle. Later it is the owner's learned model (encoders feeding a GRU,
perhaps a mixture of experts). Both consume the same signal stream, so swapping them changes
nothing in Core, the local model's prompts or the clients.

## What exists today (source, 2026-10-05)

| Signal | Where it is produced now | Notes |
|---|---|---|
| Discrete pose intent | `MotionChoice` (`src/sora/contracts/motion.py`): `wave`, `sit`, `lean`, `climb`, `stand`, `walk`, `none` | Chosen by a separate small-model call; mapped to `EmbodimentPresentationState` |
| Conversational state | `EmbodimentPresentationState`: `listening`, `speaking`, `thinking`, `waiting_for_agent`, `reading`, `typing`… | Set through `EmbodimentCommand` `SET_STATE` |
| Attention target | `LOOK_AT` / `POINT` commands with an issued desktop target, plus the attention tracker | Targets are Core-issued references, never model-invented coordinates |
| Audio / mouth | Voice worker mouth relay (W5) | Not yet a shared, timestamped envelope that a motion model could read |
| Emotion | None | Not modelled anywhere yet |
| Physical feedback | `EmbodimentFeedbackEvent`: grabbed, fell, landed… | Flows from the avatar back to Core |

## Proposed signal stream (`MotionSignal`, version 1)

One small, strict contract that Core emits at most ~30 times per second, or on change. Every field
is semantic; none is a joint, bone or renderer state name.

| Field | Type | Meaning |
|---|---|---|
| `at` | UTC timestamp | When the signal applies |
| `intent` | enum: `idle`, `wave`, `sit`, `lean`, `climb`, `stand`, `walk`, `point`, `look`, `present` | What she is deliberately doing. The superset of today's `MotionKeyword` plus `point`/`look`/`present` |
| `intent_target` | issued target reference or `null` | Core-issued window/control/pointer target, already revalidated |
| `conversation` | enum: `idle`, `listening`, `thinking`, `speaking`, `waiting_for_agent` | Turn-taking state |
| `emotion` | `{valence: -1..1, arousal: 0..1, label: optional short enum}` | Neutral `{0, 0.3}` until a source exists. The deterministic layer may ignore it |
| `attention` | `{target: reference or null, salience: 0..1}` | Where her attention is, separate from a deliberate `look` intent |
| `audio` | `{rms: 0..1, voiced: bool}` per frame, or `null` when silent | Her own speech envelope, from the TTS output. Not the owner's microphone |
| `context` | `{monitor_id, support_surface_id or null}` | Where her body is, from the topology and support surfaces |

Output of any motion layer, outside Core: joint rotations or Unity states. These never come back
into Core except as `EmbodimentFeedbackEvent`.

## How the two motion layers consume it

- **Deterministic layer (V1).** A pure mapping: `intent` → today's presentation states and
  `MOVE_TO`/`LOOK_AT`/`POINT` commands; `conversation` → listening/speaking/thinking states;
  `audio.rms` → mouth open. `emotion` is ignored. This is what exists, re-expressed against one
  input.
- **Learned model (after A Levels).** Encoders per field (intent embedding, emotion vector, audio
  frames, context) feed the owner's GRU, which outputs joint rotations. Skill experts (getting
  up, leaning, climbing) gate on `intent`. It replaces the deterministic layer wholesale.

## Steps (small; none is required to pass V1)

1. Add `MotionSignal` to `src/sora/contracts/` and export its schema.
2. Emit it from the places that already set presentation state (motion choice, voice start/stop,
   agent waiting, look/point dispatch), in a focused module rather than in `service.py`.
3. Make the deterministic Unity path read only `MotionSignal`, with today's commands as its
   implementation.
4. Merge the separate motion-keyword model call behind the decision layer after V1
   (realignment drift item 5); the signal does not change when that happens.

## Open questions for the owner

- Should `emotion` have a fixed label set (e.g. happy, curious, concerned, tired) as well as
  valence/arousal, so persona writing can refer to it?
- Should the learned model also see the owner's speech envelope (to react while listening), or
  only hers?
