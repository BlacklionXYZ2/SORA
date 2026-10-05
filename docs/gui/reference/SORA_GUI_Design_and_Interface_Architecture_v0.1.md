# SORA GUI Design & Interface Architecture — v0.1

**Date:** 3 October 2026  
**Status:** Approved GUI baseline + recorded proposals/deferred architecture

## Core premise

> SORA is not an app. SORA is a desktop presence. The windows are instruments that she and the user can summon around that presence.

## 1. Core design philosophy

- SORA's native/default state is completely windowless: her physical/avatar presence exists directly on the desktop.
- Chat, Memory, Automations and Settings are separate summonable floating windows.
- Closing Chat does not close SORA.
- The interface is a shared visual workspace between the user and SORA, not merely a control panel used to operate her.
- Simple surface, complete depth: advanced controls are hidden by default, not removed.
- All first-class windows share one visual/interaction grammar.
- SORA can open, focus, navigate, inspect, point at, pulse, highlight, annotate or close her own panels, but user-controlled state changes require explicit user action/permission.
- The GUI should expose SORA's state without turning the default interface into a debug dashboard.

## 2. Inspiration and design direction

### N.E.K.O
Keep the character-first desktop presence, floating chat and separate windows. Improve discoverability, navigation consistency and the transition into technical/admin interfaces. Avoid cryptic controls and disconnected-looking sub-applications.

### Nothing OS
Borrow restraint, a small recognisable visual vocabulary, readable typography and selective accent usage. Identity should come from a few deliberate motifs, not every control looking futuristic.

### Teenage Engineering
Borrow the idea of representing abstract subsystem state visually and instrument-like. Do not copy cryptic controls that make basic configuration hard to discover.

### Blender
Borrow task-specific views/workspaces. Do not copy permanent maximum information density.

### Unreal Editor
Borrow contextual inspectors, central spatial anchoring and temporary/detail surfaces. Do not copy heavy editor chrome into the everyday interface.

### Game HUD / diegetic UI
Attach information to the thing it describes where possible. Avoid fake holographic clutter that reduces clarity.

## 3. Interface depth model

```text
DEPTH 0 — PRESENCE
    SORA only. No application window or permanent navigation.

DEPTH 1 — INTERACTION
    Floating chat and transient conversational surfaces.

DEPTH 2 — SYSTEMS
    Settings, Memory, Automations and other panels.

DEPTH 3 — INTERNALS (deferred)
    CLI, tools, runtime, debugging, model internals, APIs, telemetry.
```

## 4. Approved visual direction

- Dark translucent/glass-like panels.
- Dark neutral base rather than pure black.
- Restrained cyan/blue accents for state, selection, active controls and SORA's pulses/highlights.
- Thin low-contrast borders and subtle shadows.
- Rounded floating windows without excessive “bubble” styling.
- Conventional highly readable sans-serif typography.
- Minimal application chrome and generous breathing room.
- Short fades, slight positional movement and small scale/opacity changes when panels appear; no excessive hologram effects.
- Information density rises with depth: Chat remains airy; Settings/internals can become dense when deliberately expanded.

## 5. Window model

- No permanent launcher/sidebar in SORA's native state.
- Panels may be opened by asking SORA, interacting with SORA directly, keyboard shortcuts, a summonable command/radial menu, or by SORA when contextually relevant.
- User-opened windows should remember useful placement.
- SORA-opened windows should appear near her without covering her.
- Related panels may form a spatial chain: SORA -> primary panel -> inspector/details panel.
- Multiple windows should arrange predictably instead of stacking randomly.

## 6. Chat

Chat is the least application-like surface and should feel like an extension of an existing conversation.

- Compact and expanded modes.
- Closing Chat does not stop SORA.
- Tool calls normally appear as small collapsed activity chips, e.g. `Searched memory · 3 results` or `Opened Memory panel`.
- Simple text/microphone/send input; multimodal controls should not clutter the default surface.
- Expanded mode can expose history, attachments, multimodal context and tool activity.

## 7. Memory

Top-level modes: **Overview | Graph | Search**.

Graph mode represents real memory relationships rather than decorative AI imagery.

- Nodes: actual memories or meaningful clusters.
- Edges: real relationships from SORA's memory system.
- Potential encodings: size = importance; brightness = current relevance; edge strength = relationship confidence/frequency.
- When SORA retrieves a memory while Graph is visible, the relevant node may activate/pulse.
- Selecting a memory opens an inspector containing ID, content/snippet, created date, importance, relevance, and connections.
- SORA may point to, pulse, highlight or trace relationships in the graph while speaking.

## 8. Automations

Automations should be a clean operations dashboard.

- Show active/paused automations, schedule/trigger, last-run status and next run where applicable.
- Selecting one exposes Overview, Edit and Logs/details.
- Progressive detail: Overview -> Schedule/Trigger -> Behavior -> Tools -> Execution history -> raw/internal configuration.
- Normal users see simple concepts such as “Every day at 08:00”; advanced users can inspect conditions, prompts, tool permissions, retries, failures and logs.

## 9. Settings

Settings is intentionally the most conventional panel because configuration should prioritise clarity.

Proposed navigation:

```text
General
Appearance
Models
Audio
Vision
Memory
Tools
Automation
Performance
Advanced
```

Model configuration uses progressive disclosure:

1. Model name, loaded state, capabilities, VRAM, Change Model.
2. Runtime/backend, context length, KV cache, memory breakdown.
3. Advanced: Flash Attention, K/V cache quantisation, GPU layers, batch/ubatch, mmap/mlock, backend overrides and raw llama.cpp arguments.

Rule: **normal choice -> technical parameters -> raw control**.

## 10. SORA's spatial interaction language

This does not depend on the future motion core; it can work with the current deterministic animation generator.

- **Point / gesture:** physical reference when practical.
- **Pulse:** brief attention marker at a point/object.
- **Anchor note:** small persistent/semi-persistent hologram-style note attached to something.
- **Highlight:** emphasise an existing control/region/object.
- **Pointer/line:** connect SORA to the referred object.
- **Relationship line:** temporarily show that two objects/memories are connected.

Implementation logistics such as hit testing, anchoring and note lifetime are deferred.

### Autonomy boundary
SORA can expose and inspect her state. The user controls modification. She may open/navigate/focus/highlight/annotate panels but should not autonomously change model settings, delete memories, enable/disable automations, etc.

## 11. Current motion/animation constraint

SORA currently uses the deterministic animation generator and will likely remain on it for most of the next year while A Levels take priority. The GUI should not depend on the future learned motion core. Deterministic pointing, pulses, panel spawning, highlights, notes and gestures are sufficient for the current design.

## 12. Model/tool architecture constraint

A core objective is retaining a roughly 2B-parameter SORA brain for low TTFT/latency. The proposed solution is to compress/filter the world before the brain rather than increasing the model size every time SORA gains capabilities.

```text
INPUT
  -> State preprocessing
  -> System-1 / Laya-class router
  -> Capability/context compiler
  -> ~2B SORA brain
  -> Action compiler
  -> Tools / GUI / deterministic animation
  -> future motion core
```

System-1 should decide capability families and whether tools/memory/visual context are required. The generative brain handles exact tool selection, arguments, sequencing and natural-language reasoning.

### Tool abstraction
The brain sees semantic actions, not implementation mechanics. For example, `present_memory(memory_id)` can internally focus Memory, switch to Graph, resolve/centre the node and trigger a highlight. Capability routing should expose only the small relevant tool subset for the current turn.

Simple, safe, high-confidence actions may eventually bypass the generative brain entirely for very low latency.

### SORA State Packet
A compact structured state packet may contain current utterance/topic/referents, foreground app, visible panels, selected object, recent memories/tools/actions, SORA state and permissions. Different subsystems consume different projections rather than all receiving the entire raw context.

## 13. Future model distribution / training

Deferred idea:

- Ship SORA with custom-tuned default brain and System-1/router models.
- Allow users to select/import compatible third-party models.
- Later build an optional **SORA Training** utility that produces a LoRA adapter for a user-supplied brain model so it learns SORA's state/tool conventions.
- The same utility could adapt/train the System-1/router for SORA-specific routing/tool use.

## 14. Deferred deeper surfaces

Possible future areas: model/runtime/context internals, tool schemas/execution, perception, memory internals/scoring, System-1 decisions, deterministic animation and later motion-core telemetry, logs, CLI and API access.

## 15. Approved baseline summary

1. SORA exists natively on the desktop with no persistent application frame.
2. Chat, Memory, Automations and Settings are separate floating windows.
3. Visual language: dark translucent glass, restrained cyan/blue, rounded corners, minimal chrome, subtle motion and readable typography.
4. Chat is lightweight/ephemeral.
5. Memory has Overview/Graph/Search and a graph inspector.
6. Automations is a clean operations dashboard with deeper configuration available on demand.
7. Settings progressively exposes LM Studio/Hermes-level control.
8. SORA can inspect and visually reference panels but not autonomously change protected settings/state.
9. Everyday surfaces stay simple; systems and internals become progressively technical.
10. Preserve the ~2B brain target by routing/filtering/compressing tools and context before the brain.

## 16. Design timeline — 3 October 2026

- Existing SORA GUI acknowledged as too rolled-together; design direction work started before implementation polish.
- N.E.K.O chosen as the primary starting reference.
- Nothing OS, Teenage Engineering, Blender, Unreal and diegetic game HUDs used as secondary references.
- Direction clarified from “N.E.K.O but cleaner” toward a state-first desktop entity with simple surface / complete depth.
- Pulse/highlight/hologram-style anchored-note idea introduced for spatial references.
- Separate-window model chosen over one monolithic/progressively expanded main window.
- Native state defined as fully windowless SORA presence.
- First-class panels defined as Chat, Settings, Memory and Automations.
- ~2B brain target reaffirmed; Laya-class System-1 routing/context filtering proposed.
- Future SORA-tuned models + LoRA training utility idea recorded for later.
- Concept art generated for Chat, Memory, Automations and Settings.
- Current visual GUI direction explicitly approved as the baseline.

## 17. Open questions

- Exact window sizes/responsiveness.
- Typography/spacing/radius/opacity/animation tokens.
- Compact vs expanded Chat behavior.
- Scalable graph layout/clustering/filtering.
- Exact permissions UX for SORA-inspectable vs user-modifiable state.
- Native/custom/hybrid OS windowing implementation.
- Multi-monitor and fullscreen behavior.
- Annotation anchoring across scroll/movement/app changes.
- Final CLI/API/developer layer.
- Learned motion-core integration after the deterministic phase.

## Recommended next step

Convert this baseline into an implementation-oriented UI specification: exact window dimensions and states, component tokens, typography and spacing system, animation timings, navigation behavior, and precise layouts for Chat, Memory, Automations and Settings.
