# What SORA can learn from Project AIRI

Written by **Opus 5.5**, 2026-10-06, at the owner's request. [Project AIRI](https://github.com/moeru-ai/airi)
by moeru-ai is a self-hosted Neuro-sama-style companion. It is further along than SORA in breadth
(desktop, web and mobile apps, VRM and Live2D, Discord/Telegram, Minecraft and Factorio agents),
while SORA is ahead on agent delegation, safety and Windows desktop control.

This is a **reference, not a plan**. Each idea says where it fits in [VISION.md](../../VISION.md)
and when it should be used. Copy ideas freely; **check AIRI's licence before copying code**
(not yet checked).

## Adopt

### 1. Spark events: the shape for SORA's proactivity

The vision wants SORA to act on her own; she has no proactivity system yet. AIRI's
`plugin-protocol` defines three event kinds that fit almost exactly:

| AIRI event | Fields | SORA use |
|---|---|---|
| `spark:notify` | `kind` (alarm / ping / reminder), `urgency`, `headline`, `payload`, `destinations` | Something worth her attention: an automation result, a build failure, a desktop event, an integration stimulus |
| `spark:emit` | `state` (queued / working / done / dropped / blocked / expired) | Progress on work. SORA's agent report-back (2026-10-06) already does this informally |
| `spark:command` | `intent` (plan / proposal / action / pause / resume), `priority`, `interrupt` (force / soft), `guidance` | A higher-level instruction to her. The vision's rule "she asks before changing things" becomes: a `command` whose intent is an action that changes files, settings or apps needs the owner's approval |

**When:** after V1, as the proactivity layer. Desktop events, automations and integrations all
publish `notify`. Core decides whether she reacts (look, speak, walk over) or stays quiet.

### 2. Module lifecycle: improve the integrations design

AIRI modules go through `module:announce` (identity, dependencies, configuration schema), then
configuration (`validate`, `plan`, `commit`), then `module:contribute:capability:offer`, then
`...:activated`. A heartbeat keeps the connection alive, and `context:update` feeds hints and
text into the character's context.

**When:** fold into [the integrations CLI design](INTEGRATIONS_CLI_DESIGN_2026-10-05.md) (after
V1). `context:update` is the same idea as that design's "stimuli".
**Leave out** AIRI's per-module permission requests and grants. They conflict with the vision:
access is set once in Settings.

### 3. Streaming speech: parallel synthesis, ordered playback

AIRI's `VoiceController` lets several speech chunks synthesise at the same time while playback
follows the order they were requested. If SORA speaks each sentence as soon as her model finishes
it, she starts talking almost at once instead of after the whole reply.

**When:** V1 (step 3, voice). This is the most useful item here for V1.

### 4. Five-vowel lip sync

`model-driver-lipsync` uses wLipSync to turn audio into stable **A, E, I, O, U** weights, with
silence detection and smoothing. It leaves the mapping to blendshapes to each renderer. SORA today
drives one shape (`aa`) from loudness. VRM has exactly these five vowel shapes.

**When:** with item 3. It matches [the motion interface design](MOTION_INTERFACE_DESIGN_2026-10-05.md)
(signals in, the renderer owns the body).

## Confirms what SORA already does

- AIRI's `core-agent` treats "one model call plus every tool call it triggered" as one round, and
  stores it only once everything has settled. SORA's companion turns do the same.
- It keeps system instructions separate from app-supplied context, so the context cannot inject
  instructions. SORA's context compiler does the same.

## Later

- **Semantic memory.** AIRI has `memory-pgvector`. SORA's memory recall is literal text matching.
  A local equivalent is a small embedding model with vectors in SQLite. It is after V1, and the
  memory graph needs it.
- **Game agents** (Minecraft, Factorio, Kerbal) match the vision's long-term "interact with games
  where APIs permit".
- **Mobile and web stages** match SORA's frozen PWA and the phone work, after V1.

## Not for SORA

The Electron/Vue stack (SORA is a native shell with web panels), Postgres/Redis (SORA is local
SQLite by design), and cloud TTS providers (SORA's voice is local).

## Sources

- [moeru-ai/airi](https://github.com/moeru-ai/airi) and its [packages](https://github.com/moeru-ai/airi/tree/main/packages)
- [`plugin-protocol` events](https://raw.githubusercontent.com/moeru-ai/airi/main/packages/plugin-protocol/src/types/events.ts)
- [`core-agent`](https://github.com/moeru-ai/airi/tree/main/packages/core-agent),
  [`model-driver-lipsync`](https://github.com/moeru-ai/airi/tree/main/packages/model-driver-lipsync),
  [`memory-pgvector`](https://github.com/moeru-ai/airi/tree/main/packages/memory-pgvector)
