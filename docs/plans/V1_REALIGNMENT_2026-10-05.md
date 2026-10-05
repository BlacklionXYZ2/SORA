# Plan realignment to the vision and V1

Prepared by **Opus 5.5**, 2026-10-05, at the owner's request. Every open task in the GUI roadmap,
the implementation plan and the W1–W6 vision-alignment workstreams is checked against
[VISION.md](../../VISION.md) and [V1.md](../../V1.md).

**Nothing has been deleted, unticked or renumbered.** This document assigns priority and flags
conflicts. The owner decides on the conflicts.

Labels:
- **V1:** needed to pass the V1 acceptance test (step numbers in brackets).
- **V1 (part):** only the stated part is V1; the rest comes after.
- **After V1:** keep it, don't work on it now.
- **Long term:** a vision item for much later.
- **Conflict:** the plan contradicts the vision, and the owner should confirm the resolution.

## GUI roadmap ([SORA_GUI_IMPLEMENTATION_ROADMAP.md](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md))

| Task | Label | Notes |
|---|---|---|
| GUI-0b DPI/text/accessibility review | V1 (part) [1–2] | V1: readable and usable at the owner's DPI and monitors. Screen reader and high contrast come after V1 |
| GUI-1a host lifecycle | V1 [1, 10] | Single instance, Quit and relaunch, and recovery on the owner's two monitors. The full physical matrix comes after V1 |
| GUI-1b Chat | V1 [2] | Typing, transcript, Stop and history. IME comes after V1 |
| GUI-1c retained workflows | V1 (part) [6] | V1: agent selection, activity, result and cancel. Board, Content, Integrations and run history keep working, but their native acceptance comes after V1 |
| GUI-1d Voice | V1 [3] | |
| GUI-2a–d Settings | V1 [7–8] | Model, voice, access and agent categories, with native save, restart and reload. Add the custom-endpoint settings |
| GUI-3a/3b Memory browser, correction and forget | After V1 | Already built and component-tested. V1 needs memory itself (step 9), not this window |
| GUI-3c `present_memory` and chips | After V1 | |
| GUI-4a–c Automations | After V1 | 4a/4c source work stays as it is. **4b (the Automations window) is no longer "next"** |
| GUI-5a/5b memory graph, pulses | After V1 | Pulses and notes fall under "desktop pings and anchored notes" |
| GUI-5c visual consistency | V1 (part) [1–2] | Presence, Chat and Settings should look finished. The other panels come after V1 |
| GUI-6a host as ordinary launch | V1 [1] | This is central to V1 |
| GUI-6b fault/restart matrix | V1 (part) [10] | V1: restart, reconnect, and model or agent failure. Sleep, fullscreen and the full DPI matrix come after V1 |
| GUI-6c voice end to end; live specialist flow | V1 [3, 6] | |
| GUI-6d regression and walkthrough | V1 | Becomes the dated V1 acceptance record |

## Implementation plan ([SORA_IMPLEMENTATION_PLAN.md](../../SORA_IMPLEMENTATION_PLAN.md))

| Task | Label | Notes |
|---|---|---|
| P06.2/P06.3 local-only routing | **Conflict → V1 [6]** | The vision says hosted agents may receive private context. The "local-only" restriction on agents should go; remote, guest and public restrictions stay. The plan criterion and the two strict expected failures in `tests/verification/` must change together |
| P15.2 phone over a private network | After V1, **frozen** | Implemented and in review; physical phone acceptance is still open. The PWA is frozen with the other non-native clients |
| P15.7 full app / settings parity | **Resolved: superseded** | Owner decision 2026-10-05: "for now, there should only be the native app (which may consist of multiple windows)". The Shell host is the only client that gets work. The full app, widget and PWA are frozen: kept and still building, but not developed, and no parity gate. Settings work continues as GUI-2 in the Shell host |
| P15.8 note-board agent edits | After V1 | |
| P15.9 NekoVerse | Long term | |
| P15.10 extension management UI | **Resolved: replaced** → after V1 | Owner decision 2026-10-05: an owner-facing CLI exposing SORA's internals for building integrations. See the [integrations and CLI design](INTEGRATIONS_CLI_DESIGN_2026-10-05.md) (MCP-based integrations, `sora dev` CLI, and later a Settings page) |
| P15.11 public harness adapter | **Resolved: replaced** → V1 [7] | Built as V1 custom agent endpoints (port, default model, description, nickname, spoken aliases) via generic OpenAI-compatible and Agent Client Protocol adapters. No public-SDK documentation |
| P15.12 object/social/typing animation polish | After V1 | |
| Claude adapter (never built) | V1 [6] | Headless Claude Code with a subscription, following the Antigravity CLI adapter pattern |

## Vision-alignment workstreams ([tracker](../verification/FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md))

| Workstream | Label | Notes |
|---|---|---|
| W1 static access | V1 | Already the direction: settings, not permission requests. Finish removing grant prompts on the local path |
| W1 ordinary startup | V1 [1] | Same goal as GUI-6a; do it once |
| W2 delegation and project paths | V1 [6] | Real project work, cancel, results reported back |
| Model/tool catalogue | V1 [6] | Plus names **Cody, Hermes, Aggie, Claude**, nicknames and spoken aliases |
| W4 native perception | V1 [4] | Screen with every prompt is the V1 part. Interval refreshing and acting on changes come after V1 (proactivity) |
| W3a semantic tools | V1 (part) [5] | Pose, walk, look and point. Press and type from chat come after V1 |
| W3b/c broad desktop interaction | After V1 | |
| W5 Windows voice | V1 [3] | |
| W6a GUI truth | V1 [2] | |
| W6b companion presence | V1 (part) [1, 5] | Basic avatar controls (show/hide, monitor, scale). Proactivity comes after V1 |
| Memory and records audit | V1 (part) [9] | Memory survives a restart and is recalled |

## Conflicts and drift to resolve (owner)

1. **Local-only routing (P06).** Resolved in conversation: hosted agents are trusted. Pending
   implementation as a V1 task.
2. **Four desktop surfaces (P15.7).** Resolved 2026-10-05: only the native app (the Shell host,
   possibly with several windows). The full app, widget and PWA are frozen, not deleted.
3. **"Public" features (P15.10, P15.11).** Resolved 2026-10-05: P15.11 becomes V1 custom
   endpoints; P15.10 becomes the owner's [integrations CLI](INTEGRATIONS_CLI_DESIGN_2026-10-05.md),
   after V1.
4. **The original spec's fast dialogue model.** The spec names hosted GPT-5.6 Luna as a dialogue
   option. The vision says one local brain only. Hosted chat backends can remain as a
   configuration option, but local is the default and the only one planned for. (Recorded; no
   action needed.)
5. **Separate small classifiers.** Motion choice, screen-view choice and the memory chooser are
   separate model calls. They should converge behind the decision layer's interface after V1. Add
   no new ones.
6. **Motion interface.** The deterministic animation layer should consume the same semantic
   signals the owner's motion model will (intent, emotion, attention, speaking/listening, audio).
   Writing that interface down is small and keeps the learned model a drop-in replacement.
   Recommended before or during V1 step 5.
7. **Persona.** The identity files total 111 words, written as engineering policy. The owner will
   write the persona later. V1 will sound generic until then.
8. **Security model.** The spec's "Level 3 interaction needs stronger approval" is replaced by the
   vision's rule: she may act freely, but asks before changing files, settings or apps.
   Guardrails target the small local brain, not the agents.
