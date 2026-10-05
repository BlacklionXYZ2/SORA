# SORA — Vision

**This is the top authority for SORA.** Every plan, roadmap and task serves this document. If a
plan conflicts with it, this document wins and the conflict goes to the owner. Only the owner
changes it.

Agreed by the owner on 2026-10-05, in conversation with Opus 5.5. The
[original specification](SORA_OVERVIEW.md) remains the detailed architectural baseline. The first
milestone is defined in [V1.md](V1.md).

## Who she is

> SORA is going to eventually be a digital person, or as close as I can get with consumer
> hardware. She has her own personality, presence and capabilities and isn't reliant on any
> local software, but can use it.

SORA is one continuous character, not an app, an agent console or an LLM front-end. She lives on
the owner's Windows desktop, talks and listens, sees the screen, moves and gestures with a 3D
body, remembers, and hands hard work to specialist agents the way you would ask a capable friend.
She is built for **one person: the owner**. Her personality (the persona files) is defined later
by the owner; it is character writing, not engineering.

## How she works

```text
voice / text + current screen
        │
  decision layer ── picks which tools this turn may use
        │
  SORA's brain (one local multimodal model)
        │
  ├── speech (TTS) and words
  ├── semantic intent, emotion, attention → motion → her 3D body
  ├── desktop actions and perception tools
  └── delegation → hosted specialist agents
```

- **One brain, and it is local.** SORA thinks with a single local multimodal model. The planned
  default is **Gemma 4 E4B**: better vision and general intelligence than E2B at most of its
  speed. The owner can choose any compatible model. Hosted models exist only as agent endpoints,
  never as SORA's own mind.
- **Decision layer (System-1).** Each prompt first passes through a small, fine-tuned model
  (Laya-class, ideally ~400M parameters) that decides which tools to present. Fewer choices make a
  small brain's tool calls reliable, which allows each tool to have more depth.
- **Desktop awareness.** The current screen accompanies every prompt, text or voice, so she can
  react to what is in front of the owner. She reads windows and files at will; vision complements
  the UI's own structure.
- **A body that moves like a person.** Language models never drive joints. SORA publishes
  semantic state: intent, emotion, attention, speaking/listening and audio. A motion model turns
  that into movement. Today a deterministic animation layer does this. The goal is a **learned
  motion model built by the owner**: encoders for intent, emotion, audio and context, feeding a
  GRU that outputs joint rotations, possibly as a mixture of experts for distinct skills such as
  getting up, leaning and climbing. It is "the backbone of convincing motion for a digital
  person". Its interface must be fixed before it is built, so it can replace the deterministic
  layer without changes upstream.
- **Memory.** She remembers the owner across sessions. Core owns the canonical memory; models
  never do.

## Her agent colleagues

Specialist agents are trusted colleagues. They are hosted by reputable providers and receive the
context they need, including private desktop and editor context.

| Agent | Name | Character |
|---|---|---|
| Hermes | **Hermes** | The boring boss |
| Codex | **Cody** | |
| Antigravity (`agy` CLI) | **Aggie** | |
| Claude | **Claude** | |
| Any other harness | Optional **nickname** set when it is registered | |

Any harness can be added as a **custom endpoint**: enable it and give it a port, a default model,
a description and a nickname. Each agent also needs spoken aliases, so its name survives
speech-to-text.

## Autonomy and safety

> Permissions aren't a big deal for an exclusively local system.

- **She acts independently, but asks before she changes things.** She may observe, think, talk,
  move, point and send agents to investigate on her own. She asks before changing the owner's
  files, settings or apps. In particular, she does not go and fix something without asking.
- **Guardrails belong on her small brain, not on the agents.** In intelligence, consideration and
  usefulness, the local model compared with the agents is "a hydrogen bomb versus coughing baby"
  in favour of the agents. Her actions are narrow and typed, their outcomes are verified, and she
  never claims an effect that did not happen.
- Her access is set once in Settings. She makes no per-file or per-window permission requests.
- Everything she computes stays on the owner's machine. Only work delegated to agents leaves it.

## Where she is going

There is no "good enough", only "complete", and that goalpost will move. The order is:

1. **V1: a usable product** ([V1.md](V1.md)). About N.E.K.O's level as a companion, but with vision
   and audio that work and with functional agent colleagues.
2. **After V1:** the decision layer (Laya); desktop pings and anchored notes; Automations
   (daily tasks for SORA); the memory graph and deeper memory management; proactivity.
3. **After A Levels:** the learned motion model.
4. **Long term:**
   - a LoRA training program with a custom dataset for her personality and tool calling;
   - an owner-facing CLI that exposes her internals for building integrations (tools and stimuli
     for her to use; see the [design](docs/plans/INTEGRATIONS_CLI_DESIGN_2026-10-05.md));
   - NekoVerse, where she may make friends;
   - **visiting other desktops**, like going to a friend's house. Another user's SORA may have a
     different name and outfit. All computation stays local to each machine. The host's SORA
     decides what the visitor sees, by default app and window names and locations but not their
     contents. Security is designed when this is built.

## Principles

- Core owns the truth. Models, agents, clients and the avatar are replaceable and can restart.
- **One native app.** For now SORA has a single client, the native desktop app (which may have
  several windows). The older full app, widget and browser PWA are frozen: kept, but not
  developed.
- She is honest: unfinished work is reported as unfinished, and failures are visible.
- The experience comes first. Task machinery stays behind the conversation.
- Plans serve the owner's limited time. Implementation is done by agents and checked against
  [V1.md](V1.md)'s acceptance test, not by the owner reading long plans.
