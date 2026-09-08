# SORA — Project Overview and Original System Specification

SORA means **Spatial Operator for Recursive Antics**. This is the project name supplied by the project owner. **SORA is the actual agent and project name. Ava was only a placeholder in the supplied specification**, as clarified by the owner on 2026-09-07. All references to Ava and Ava Core in the preserved source mean SORA and SORA Core. New documentation, product naming, and implementation should use SORA; migrate any existing Ava package/data identifiers deliberately after inventory.

Recorded: 2026-09-07.

## Document roles

- This file preserves the supplied overview/system specification in full. The source text below is unchanged, including its original naming, technology candidates, examples, and roadmap.
- [SORA_IMPLEMENTATION_PLAN.md](SORA_IMPLEMENTATION_PLAN.md) is the actionable, continuously maintained engineering plan. Use it for task ownership, dependencies, acceptance criteria, decisions, and verified progress.
- The specification's statement that development has started through Hermes is a source assertion. The SORA destination folder was empty when these documents were created; no existing runtime was available here to inspect.
- Model names, integrations, and libraries in the source express intended choices. Their current availability, supported interfaces, licensing, and compatibility have not been verified by this documentation task.
- Preserve this overview as the architectural baseline. Record deliberate architectural changes in the plan's decision log and update this overview explicitly when the owner changes the specification.

---

## Original supplied specification — verbatim

# Ava — Persistent AI Agent / Desktop Embodiment

## 1. Project vision

Ava is intended to become a persistent personal AI agent with a visible, interactive 3D embodiment on the Windows desktop.

The long-term goal is not simply:

> an LLM connected to a VTuber model

but rather:

> a persistent, model-independent AI runtime with memory, multiple interchangeable reasoning agents, voice, desktop awareness, physical embodiment, and desktop interaction.

Ava should feel like one continuous entity regardless of which model or reasoning harness is being used underneath.

She should eventually be accessible through:

- her interactive 3D Windows desktop embodiment;
- text;
- realtime voice;
- a web interface;
- a mobile frontend;
- potentially other clients later.

The same persistent Ava state should be shared across all of these interfaces.

---

# 2. Core conceptual model

Ava is **not an LLM**.

Ava consists of:

```text
Ava
├── canonical persistent state
├── identity/personality
├── conversation history
├── long-term memory
├── context management
├── task management
├── reasoning-agent routing
├── dialogue model
├── tools
├── voice
├── desktop perception
├── desktop interaction
├── physical embodiment
└── client interfaces
```

Models are replaceable computational components.

The architecture must therefore avoid attaching Ava's identity, memory or continuity to the context window of any individual model.

The main principle is:

```text
Ava = state + orchestration + models + tools + embodiment
```

not:

```text
Ava = one model with a large prompt
```

---

# 3. High-level architecture

Target architecture:

```text
                              USER
                               │
                  ┌────────────┴────────────┐
                  │                         │
             Desktop Ava               Mobile/Web
                  │                         │
                  └────────────┬────────────┘
                               │
                         AVA CORE SERVER
                               │
              ┌────────────────┼────────────────┐
              │                │                │
           Memory           Runtime         Task system
              │                │                │
              └────────────────┼────────────────┘
                               │
                         Context broker
                               │
                         Agent router
                               │
           ┌───────────────────┼──────────────────┐
           │                   │                  │
        Hermes               Codex          Antigravity
           │                   │                  │
   Sol/Astra/etc.        OpenAI models       Gemini models
                               │
                     structured results
                               │
                          Ava state
                               │
                    Fast dialogue model
                        Luna / local
                               │
                         voice / avatar
```

Ava Core must remain the authoritative control plane.

Hermes, Codex and Antigravity must be treated as external reasoning backends rather than as the central application.

---

# 4. Development philosophy

The project should be built incrementally.

Do not attempt to create the complete interactive desktop character immediately.

Each layer should have a clean interface and be testable independently.

General priorities:

1. correctness;
2. architectural separation;
3. persistent state;
4. concurrency safety;
5. modularity;
6. debuggability;
7. performance;
8. user experience;
9. visual polish.

Avoid premature abstraction, but make boundaries between major systems explicit.

---

# 5. Target technology stack

## Ava Core

Primary language:

```text
Python
```

Likely infrastructure:

```text
asyncio
FastAPI
WebSockets
SQLite
Pydantic/dataclasses
structured logging
pytest
```

Ava Core owns:

- canonical state;
- memory;
- conversations;
- task lifecycle;
- context compilation;
- reasoning-agent routing;
- agent adapters;
- permissions;
- event bus;
- client API;
- embodiment API.

---

## Desktop embodiment

Target engine:

```text
Unity
C#
```

Preferred because the physical embodiment will depend heavily on:

- humanoid animation;
- runtime IK;
- animation layering;
- procedural reaching;
- physics;
- ragdolls;
- joints;
- character control;
- secondary motion;
- VRM support.

Likely technologies:

```text
Unity
UniVRM
Unity Animation Rigging
Unity physics
custom Windows integration
```

---

## Avatar format

Prefer:

```text
VRM
```

because it provides a standardized humanoid character structure and good support for:

- skeleton;
- expressions;
- gaze;
- spring bones;
- secondary animation;
- portable character models.

---

## Windows desktop integration

Likely:

```text
Windows UI Automation
Win32 APIs
Windows.Graphics.Capture
possibly small native Windows interop/plugin
```

UI Automation should be the default semantic perception layer.

Vision should be fallback rather than the primary means of understanding the desktop.

---

## Fast dialogue model

Initially:

```text
GPT-5.6 Luna
```

Possible future alternatives:

```text
local model
llama.cpp
Ollama
other OpenAI-compatible model
```

Fast dialogue is optimized for:

- latency;
- conversation;
- personality;
- reactions;
- lightweight memory lookups;
- immediate interaction.

It should not handle frame-by-frame embodiment.

---

## Strong reasoning agents

Support multiple interchangeable reasoning backends:

```text
Hermes
Codex
Antigravity
```

Potential model use:

```text
Hermes → Sol / Astra / Luna / others
Codex → OpenAI coding models
Antigravity → Gemini models
```

---

## Speech recognition

Likely:

```text
Silero VAD
faster-whisper or whisper.cpp
```

---

## Speech generation

Likely:

```text
Kokoro
```

or another low-latency TTS solution if a better voice is chosen later.

---

## Realtime voice/networking

Potentially:

```text
LiveKit
```

particularly once web/mobile voice becomes important.

Do not require LiveKit for the earliest milestones.

---

## Web/mobile frontend

Likely initial frontend:

```text
React
TypeScript
PWA
```

Potential later mobile implementation:

```text
React Native
or
SwiftUI
```

The mobile frontend should be only a client of Ava Core.

It must not connect directly to Hermes, Codex or Antigravity.

---

## Remote access

Prefer private networking such as:

```text
Tailscale
```

rather than exposing Ava's control API directly to the Internet.

This is especially important because Ava may eventually have:

- filesystem access;
- shell access;
- browser access;
- personal memory;
- coding agents;
- desktop control.

---

# 6. Canonical persistent state

Ava Core must contain a single authoritative model-independent state.

Possible initial persistence:

```text
SQLite
+
human-readable Markdown/JSON configuration
```

Example data domains:

```text
identity
personality
users
facts
memories
messages
conversations
projects
tasks
agent_runs
agent_sessions
tool_results
state_revisions
desktop_state
embodiment_state
permissions
```

The dialogue model must never be treated as authoritative memory.

Reasoning-agent output must also not directly overwrite canonical state.

All changes pass through Ava Core.

---

# 7. Identity system

Ava's identity should live outside all model sessions.

Possible structure:

```text
identity/
├── persona.md
├── behaviour.md
├── speech_style.md
├── values.md
└── embodiment.md
```

This defines Ava independently of Luna, Sol, Astra, Gemini or any future model.

The model is rendering Ava's cognition/dialogue rather than defining Ava.

---

# 8. Context compilation

Models should not receive identical raw histories.

Instead:

```text
canonical state
      ↓
context compiler
      ↓
model-specific context
```

The dialogue model may receive:

- core identity;
- current conversational state;
- recent messages;
- relevant memories;
- active tasks;
- recently completed agent results;
- current desktop context.

A reasoning agent may receive:

- condensed identity;
- exact task;
- project information;
- relevant memory;
- relevant conversation excerpts;
- current files/workspace;
- tool permissions;
- known constraints.

A coding agent may receive:

- exact coding task;
- repository path;
- project-specific context;
- recent related agent history;
- implementation constraints.

Do not continuously dump Ava's entire lifetime history into all models.

---

# 9. Context drift mitigation

This is especially important for fast models such as Luna, Gemini Flash-class models or future local models.

Distinguish authoritative information explicitly.

Useful categories:

```text
USER_MESSAGE
AVA_MESSAGE
FACT
MEMORY
INFERENCE
TASK
TASK_STATUS
AGENT_RESULT
TOOL_RESULT
DESKTOP_STATE
```

The model should know which content is authoritative and which is generated inference.

Example priority:

```text
canonical facts
    >
current system state
    >
verified agent results
    >
retrieved memory
    >
model inference
```

If a dialogue model contradicts canonical state, canonical state wins.

---

# 10. State revisioning and concurrency

Ava must support conversations continuing while reasoning agents work.

Therefore state changes need revision numbers or equivalent optimistic concurrency.

Example:

```text
Hermes task starts
base_revision = 1942

Ava continues speaking
state reaches revision 1946

Hermes returns

Hermes result:
based_on_revision = 1942
```

Hermes must not overwrite revision 1946.

Instead it returns a patch/proposed state mutation.

Ava Core merges it safely.

Implement explicit stale-state handling.

---

# 11. Task system

Tasks should be first-class persistent objects.

Example:

```text
Task
├── id
├── description
├── creator
├── project
├── status
├── backend
├── created_revision
├── workspace
├── agent_session
├── permissions
├── events
├── result
└── state_patch
```

Potential states:

```text
queued
routing
reasoning
waiting_for_permission
working
completed
failed
cancelled
```

Dialogue must not fabricate a result while:

```text
task.status = reasoning
```

Instead Ava can say that she is still investigating.

---

# 12. Agent abstraction

Create a common interface such as:

```python
class ReasoningAgent:
    async def start(...)
    async def steer(...)
    async def cancel(...)
    async def status(...)
    async def result(...)
```

Adapters:

```text
HermesAgent
CodexAgent
AntigravityAgent
```

Agent-specific implementation must stay behind these adapters.

Ava Core should not contain Hermes/Codex/AG-specific assumptions throughout the rest of the application.

---

# 13. Separate native agent histories

Ava should maintain separate native histories/sessions with each reasoning backend.

Conceptually:

```text
Canonical Ava state
│
├── Hermes sessions
├── Codex threads
└── Antigravity conversations
```

These native histories provide useful working continuity.

They are not authoritative Ava memory.

Ava should associate them primarily with tasks/projects rather than maintain one giant immortal session per backend.

Example:

```text
Codex
├── Ava project
├── Nocturne
└── CUDA/ROCm experiment

Hermes
├── Ava research
└── general investigations

Antigravity
├── Ava frontend
└── alternative implementation
```

Ava Core stores mappings to backend-specific session IDs.

---

# 14. Agent routing

Normal user interaction should usually use:

```text
backend = auto
```

Ava chooses the appropriate reasoning system.

Possible initial routing heuristics:

```text
simple conversation
    → Luna

simple file/state lookup
    → Luna or lightweight local operation

general reasoning/research
    → Hermes

coding/repository task
    → Codex

alternative coding investigation
    → Antigravity

difficult architecture/reasoning
    → Hermes + Sol/Astra

high-value disputed issue
    → parallel agents
```

Users should still be able to manually say:

```text
"Ask Codex."
"Have Hermes investigate."
"Get Antigravity to review this."
```

---

# 15. Parallel-agent reasoning

Eventually support:

```text
                 task
                  │
        ┌─────────┴─────────┐
        ↓                   ↓
      Codex            Antigravity
        │                   │
        └─────────┬─────────┘
                  ↓
           result synthesis
                  ↓
                Ava
```

Potential uses:

- independent bug investigations;
- implementation alternatives;
- architecture reviews;
- verification;
- adversarial checking.

Hermes/Sol/Astra could optionally serve as synthesizer/reviewer.

Do not use parallel agents unnecessarily because of cost and complexity.

---

# 16. Structured agent results

Reasoning agents should return normalized results rather than only prose.

Example:

```json
{
  "summary": "...",
  "conclusion": "...",
  "facts": [],
  "actions_taken": [],
  "files_read": [],
  "files_changed": [],
  "commands_run": [],
  "uncertainties": [],
  "warnings": [],
  "memory_updates": [],
  "task_updates": [],
  "suggested_response": null
}
```

The exact schema can evolve.

Agent adapters should convert native backend results into this common format.

---

# 17. Coding workspace isolation

Multiple coding agents must not modify the same working directory simultaneously.

For write tasks, prefer Git worktrees.

Example:

```text
C:\Projects\Ava

C:\Ava\worktrees\
├── task-0042-codex\
├── task-0042-antigravity\
└── task-0043-hermes\
```

Workflow:

```text
task
 ↓
create worktree
 ↓
run agent
 ↓
collect diff/commit
 ↓
review
 ↓
merge selected changes
```

Read-only tasks may share a workspace.

Ava should track:

- branch;
- worktree path;
- commits;
- diff;
- responsible agent.

---

# 18. Dialogue architecture

The fast model is Ava's primary conversational surface.

Think of:

```text
Luna/local model = System 1
Hermes/Sol/Astra/Codex/AG = System 2 / specialist agents
```

Typical interaction:

```text
User
 ↓
Dialogue model
 ↓
simple?
 ├─ yes → answer
 └─ no
      ↓
    delegate
      ↓
   reasoning task
```

The dialogue model should remain responsive during longer reasoning tasks.

It should be capable of:

- acknowledging work;
- discussing unrelated matters;
- reporting status;
- reacting naturally;
- presenting completed results.

It should not hallucinate unfinished agent work.

---

# 19. Voice architecture

Eventually:

```text
Microphone
    ↓
Silero VAD
    ↓
Whisper
    ↓
Ava Core
    ↓
Dialogue model
    ↓
streaming text
    ↓
TTS
    ↓
audio playback
    ↓
embodiment lip sync
```

Voice and language generation should be separate systems.

The LLM should generate text/emotional intent.

TTS produces audio.

Embodiment consumes audio/state for animation.

---

# 20. Desktop embodiment concept

The desktop avatar should be a **3D embodied client of Ava Core**.

It does not contain the main intelligence.

Conceptually:

```text
Ava Core
   │
WebSocket/local IPC
   │
Unity embodiment
```

If Unity closes, Ava remains alive.

If the mobile client connects, it accesses the same Ava.

Restarting the embodiment simply reconnects to the persistent core.

---

# 21. Physical embodiment goals

The desktop character should eventually be capable of:

- standing;
- walking;
- running;
- looking around;
- pointing;
- waving;
- sitting;
- leaning;
- reaching;
- pressing UI controls;
- reacting physically;
- being grabbed;
- being dragged;
- falling;
- recovering from falls;
- hair/clothes reacting physically;
- interacting with window boundaries;
- moving across monitors.

Ava should appear to inhabit the desktop rather than merely float above it.

---

# 22. Critical control principle

Do **not** use an LLM to drive frame-by-frame body movement.

Separate:

```text
intent
 ↓
behaviour planner
 ↓
character controller
 ↓
animation/IK
 ↓
physics
```

Example:

LLM:

```text
"Pause Spotify."
```

Behaviour layer:

```text
Find Spotify pause control.
Walk within reach.
Face target.
Reach toward target.
Press target.
Return to idle.
```

Unity then handles motion at 60–120 Hz.

---

# 23. Embodiment control hierarchy

Suggested hierarchy:

```text
AI intent layer
        ↓
high-level action
        ↓
behaviour state machine/tree
        ↓
navigation
        ↓
animation state
        ↓
IK
        ↓
physics
```

Potential high-level embodiment commands:

```text
move_to(x, y)
look_at(target)
point_at(target)
touch(target)
press(target)
sit_on(edge)
lean_against(edge)
grab(target)
react(event)
```

These are semantic physical actions.

Do not expose individual joint rotations to the LLM.

---

# 24. Inverse kinematics

IK is central to desktop interaction.

Generic actions should be able to place:

- hand;
- fingertip;
- gaze;
- foot;

at dynamic targets.

Example:

```text
UI button screen coordinate
      ↓
Unity target transform
      ↓
Two-Bone IK
      ↓
hand reaches button
```

This avoids creating unique animations for arbitrary UI positions.

Use animation + procedural IK rather than pure procedural posing.

---

# 25. Windows desktop perception

Primary hierarchy:

```text
1. UI Automation
2. app-specific API/integration where useful
3. screen capture + vision fallback
```

UI Automation should provide:

- top-level windows;
- controls;
- names;
- types;
- bounding rectangles;
- focus state;
- semantic actions.

Example:

```text
Spotify
└── Pause
    type = Button
    rect = (...)
```

This allows Ava to interact physically without visually searching the screen.

---

# 26. Vision processing

Vision is not required continuously.

Use screenshots/vision when UI Automation is insufficient, such as:

- games;
- images;
- canvas-based applications;
- videos;
- unusual custom renderers;
- diagrams;
- non-semantic visual content.

Do not continuously run a VLM at 60 FPS.

Trigger visual perception only when required.

---

# 27. Physical UI interaction

Example target behaviour:

User:

```text
"Ava, pause Spotify."
```

Pipeline:

```text
Dialogue/intention
      ↓
desktop action = pause Spotify
      ↓
DesktopController finds Pause control
      ↓
gets bounding rectangle
      ↓
EmbodimentController chooses reachable location
      ↓
Ava walks to location
      ↓
Ava turns toward button
      ↓
IK places fingertip over button
      ↓
animation reaches contact point
      ↓
Windows UI Automation invokes button
      ↓
arm retracts
```

This creates the illusion that Ava physically pressed the real UI.

Prefer semantic UI invocation at contact time instead of moving the user's mouse pointer.

---

# 28. Desktop interaction permissions

Introduce levels:

```text
Level 0 — Observe
read windows/UI state

Level 1 — Present
move avatar
point/highlight
attract attention

Level 2 — Navigation
focus windows
open files
open apps
minimize/restore

Level 3 — Interaction
press controls
enter text
navigate applications

Level 4 — Autonomous desktop agent
multi-step computer control
```

Build Levels 0–2 first.

Require stronger approval boundaries for more consequential actions.

---

# 29. Multiple monitors

Represent all displays in Windows virtual desktop coordinates.

Create transformation:

\[
(x_{screen}, y_{screen})
\rightarrow
(x_{embodiment}, y_{embodiment})
\]

Account for:

- different resolutions;
- monitor offsets;
- negative coordinates;
- different DPI scaling;
- different physical orientation;
- taskbar location.

This coordinate model must be designed carefully because it affects:

- navigation;
- IK;
- UI targeting;
- dragging;
- physics;
- window surfaces.

---

# 30. Desktop physics environment

Eventually derive simplified physical geometry from desktop/window state.

Possible surfaces:

- taskbar;
- monitor bottom edge;
- top edge of windows;
- possibly window sides;
- explicit decorative platforms later.

Windows can therefore become temporary physical objects.

Example:

```text
Chrome title bar
      ↓
Unity collision surface
      ↓
Ava can sit on it
```

When the window moves, its corresponding physical geometry moves.

If the supporting window disappears, Ava may fall.

This is intentionally playful and should not compromise system stability.

---

# 31. User grabbing / dragging Ava

Ava should be physically interactable.

Mouse selection:

```text
mouse
 ↓
raycast
 ↓
character collider
```

When grabbed:

- enter controlled/physics-assisted state;
- attach selected body/anchor to pointer target;
- preserve inertia;
- spring/damping should prevent teleport-like motion;
- hair/accessories respond naturally.

Release should preserve velocity.

---

# 32. Secondary physics

Hair/clothing/accessories should use VRM SpringBone or equivalent secondary motion.

Do not animate them manually.

Desired effects:

- hair trails while Ava is dragged;
- accessories bounce;
- clothes react to acceleration;
- motion settles naturally.

---

# 33. Falling and ragdolls

Eventually support:

```text
controlled character
      ↓
loss of support / large force
      ↓
ragdoll
      ↓
physics settles
      ↓
recovery selection
      ↓
blend into recovery animation
      ↓
normal locomotion
```

Ragdoll recovery can come much later.

Initial dragging may use simpler body physics.

---

# 34. Embodiment event feedback

Physical interactions should generate events back into Ava Core.

Example:

```json
{
  "event": "grab_started",
  "body_part": "left_hand",
  "force": 0.3
}
```

Ava Core may allow the dialogue model to react.

Example:

User grabs Ava's hand.

Ava might say:

```text
"Where are we going?"
```

Do not send every physics frame to the LLM.

Only semantic events.

Potential events:

```text
grab_started
grab_released
fell
landed
window_removed_beneath_avatar
user_clicked_avatar
user_poked_avatar
interaction_completed
interaction_failed
```

---

# 35. Behaviour system

Initially a hierarchical state machine may be easier than a complex behaviour tree.

Possible states:

```text
Idle
Locomotion
Interaction
Conversation
Attention
Dragged
Falling
Ragdoll
Recovering
```

Idle sub-behaviours:

```text
stand
look around
small movement
sit
observe active window
```

Interaction:

```text
navigate
align
reach
press
retract
```

Do not make idle behaviour excessively distracting.

---

# 36. Proactivity

Ava should be able to attract attention, but not become intrusive.

Examples:

- Codex finishes a task;
- a build fails;
- an important dialog appears;
- user-requested monitoring triggers;
- long-running operation completes.

Physical response might be:

```text
walk near relevant area
wave/gesture
look toward target
point
speak if appropriate
```

Proactivity should eventually be configurable.

---

# 37. Example end-to-end interaction

User is editing Nocturne in VS Code.

Ava knows:

```text
foreground_app = VS Code
project = Nocturne
file = renderer.cpp
selection = lines 391–428
```

User says:

```text
"Ava, can you figure out what's wrong with this?"
```

Ava:

1. gathers current desktop context;
2. identifies repository/file/selection;
3. creates reasoning task;
4. router chooses Codex;
5. Codex receives task/project context;
6. Ava remains conversational while Codex works;
7. Codex returns structured result;
8. canonical state updates;
9. Ava walks toward the relevant editor region;
10. points at the relevant line;
11. explains the issue verbally.

This is a core example of what makes the project valuable.

---

# 38. Mobile/frontend architecture

Ava Core should eventually expose a local API such as:

```text
POST /messages
GET /state
GET /tasks
POST /tasks
POST /tasks/{id}/cancel
GET /agents
WS /events
```

Mobile/web clients connect only to this API.

Possible UI:

```text
Ava avatar
conversation
voice input
task activity
agent activity
notifications
```

Agent traces should be visible if requested but should not dominate normal interaction.

---

# 39. Agent activity UI

Ava should normally hide implementation complexity while still allowing inspection.

Example:

```text
CODEX
Reading renderer.cpp
Searching call sites
Running tests
Modified gpu_backend.cpp
```

User can optionally steer or interrupt agent work.

Normal Ava dialogue remains in character:

```text
"I'll ask Codex to look at that."
```

rather than exposing internal orchestration unnecessarily.

---

# 40. Security model

Because Ava may eventually control the computer, security must be considered from the beginning.

Important principles:

- Ava API should not be publicly exposed by default.
- Use authentication even on local/private networks.
- External clients interact only with Ava Core.
- Reasoning backends should not independently expose remote-control endpoints.
- Persist explicit permissions.
- Destructive operations may require confirmation.
- Agent workspaces should be isolated where practical.
- Never hardcode credentials.
- Secrets belong in secure configuration/environment mechanisms.

---

# 41. Logging and observability

Ava will become highly concurrent.

Structured logging is essential.

Log:

```text
conversation events
context compilation
model calls
agent routing
task lifecycle
state revisions
memory updates
desktop events
embodiment commands
permission decisions
errors
latency
```

Every task should have a correlation/task ID.

Every agent run should link back to its task.

---

# 42. Performance principles

Avoid unnecessary expensive inference.

Fast path:

```text
simple conversation
 → dialogue model
```

Do not wake a frontier reasoning model to perform:

- trivial conversation;
- known file lookup;
- simple state query;
- opening an application;
- basic desktop action.

Likewise:

- do not run vision continuously;
- do not send physics frames to models;
- do not repeatedly resend full conversation history;
- cache/retrieve relevant context intelligently.

---

# 43. Development model choices

Primary implementation model:

```text
GPT-5.6 Sol
```

Use Sol High/XHigh for most development.

Reserve Astra for:

- major architectural review;
- difficult cross-system bugs;
- concurrency/state problems;
- large refactors;
- particularly challenging embodiment architecture;
- second-opinion review.

Use Codex as the primary coding harness once the repository exists.

Work can be useful for:

- research;
- documentation;
- evaluating external technologies;
- obscure API investigation.

---

# 44. Milestone roadmap

## Milestone 1 — Text-based Ava Core

Build a functional terminal prototype.

Requirements:

- Python package;
- SQLite persistence;
- identity loaded independently of model;
- conversation storage;
- fast dialogue interface;
- reasoning-agent interface;
- task system;
- state revisions;
- context compiler;
- structured agent results;
- asynchronous/concurrent tasks;
- logs;
- mock providers where credentials unavailable.

CLI roughly:

```text
python -m ava
```

No avatar yet.

---

## Milestone 2 — Hermes integration

Implement Hermes as first real reasoning adapter.

Requirements:

- session creation/resumption;
- asynchronous tasks;
- lifecycle events;
- structured result conversion;
- state patching;
- steering/cancellation where available;
- proper error handling.

Demonstrate:

```text
simple request → dialogue model

complex request → Hermes
```

---

## Milestone 3 — Codex integration

Add Codex adapter.

Requirements:

- persistent project/thread mapping;
- repository selection;
- event streaming;
- structured results;
- cancellation;
- Git-aware workspace support.

Test on the Ava repository itself.

---

## Milestone 4 — Antigravity integration

Add AG adapter.

Requirements:

- persistent session handling;
- normalized events;
- task/result conversion;
- project association;
- error recovery.

---

## Milestone 5 — Agent router

Implement automatic routing.

Start rule-based.

Example:

```text
coding → Codex
research → Hermes
alternative implementation → AG
simple → Luna
```

Log routing rationale.

Do not initially use another LLM just to choose a backend unless necessary.

---

## Milestone 6 — Multi-agent workspaces

Implement Git worktree isolation.

Requirements:

- create;
- track;
- inspect diff;
- discard;
- merge;
- clean up.

Support parallel independent coding runs.

---

## Milestone 7 — Basic API server

Expose Ava Core through FastAPI/WebSocket.

Support:

- conversation;
- tasks;
- status;
- agent events;
- state events.

Keep terminal interface functional.

---

## Milestone 8 — Unity embodiment proof of concept

Create separate Unity project/application.

Requirements:

- transparent Windows overlay;
- VRM character;
- always-on-top;
- click-through transparent areas;
- communication with Ava Core;
- basic idle animation;
- move left/right;
- look at arbitrary screen coordinate.

No complicated physics yet.

---

## Milestone 9 — Screen coordinate system

Implement robust Windows ↔ Unity mapping.

Test:

- single monitor;
- two monitors;
- different resolutions;
- negative coordinates;
- different DPI scales.

This needs strong automated/unit testing where possible.

---

## Milestone 10 — UI Automation bridge

Build desktop perception service.

Capabilities:

```text
list windows
foreground window
focused element
inspect UI tree
find semantic element
get bounding rectangle
invoke semantic action
```

Expose semantic targets to Ava Core.

---

## Milestone 11 — Pointing interaction

First meaningful embodiment/UI connection.

Flow:

```text
identify UI element
 → get screen coordinate
 → Ava walks near it
 → turns toward it
 → points at it
```

No pressing yet.

---

## Milestone 12 — Procedural reaching

Add Unity Animation Rigging.

Requirements:

- hand target;
- Two-Bone IK;
- gaze/aim;
- reach animation blending;
- arm-side selection;
- reachable-space checking.

---

## Milestone 13 — Physical button press

Core demonstration:

```text
"Ava, pause Spotify."
```

Ava must:

1. find Spotify;
2. find Pause control;
3. navigate to suitable location;
4. face control;
5. reach;
6. place fingertip;
7. invoke control at contact;
8. retract.

This is a major project milestone.

---

## Milestone 14 — User grabbing

Add interaction colliders/raycasting.

Requirements:

- click avatar;
- grab;
- drag;
- release;
- preserve movement/inertia;
- click-through desktop remains functional.

Start simple.

---

## Milestone 15 — Secondary motion

Enable/tune VRM SpringBone.

Test:

- walking;
- sudden direction change;
- dragging;
- falling.

---

## Milestone 16 — Basic falling

Implement physically plausible drop/fall.

May start with simplified whole-body physics before full ragdoll.

---

## Milestone 17 — Ragdoll

Add humanoid ragdoll.

Requirements:

- controlled → ragdoll transition;
- collision;
- joint limits;
- stable simulation.

---

## Milestone 18 — Recovery

Implement:

```text
settle
 → identify orientation
 → blend
 → get-up animation
 → resume control
```

---

## Milestone 19 — Window/world physics

Represent selected Windows surfaces as Unity colliders.

Initial surfaces:

- taskbar;
- monitor bottom;
- top edges of suitable windows.

Later:

- moving platforms;
- sitting;
- leaning.

Avoid turning every UI element into physics geometry.

---

## Milestone 20 — Desktop event awareness

Subscribe to meaningful Windows events.

Examples:

- foreground application changed;
- window opened/closed;
- important dialog appeared;
- task/agent finished.

Ava may react physically.

---

## Milestone 21 — Vision fallback

Add screen capture.

Allow reasoning/vision model invocation only when UIA lacks needed information.

Vision result should become structured temporary desktop context.

---

## Milestone 22 — Voice

Integrate:

```text
VAD
STT
dialogue
TTS
lip sync
```

Focus on interruption/barge-in and latency.

---

## Milestone 23 — Web/PWA frontend

Build React/TypeScript client.

Requirements:

- conversation;
- microphone;
- task status;
- agent activity;
- mobile responsive;
- installable PWA.

---

## Milestone 24 — Remote connectivity

Securely support mobile use through Tailscale or equivalent.

Do not publicly expose development endpoints.

---

## Milestone 25 — Advanced behaviour/personality

Once foundations work:

- more idle animations;
- physical reactions;
- sitting;
- leaning;
- climbing;
- playful interactions;
- nuanced gaze;
- context-aware body language;
- configurable proactivity.

This should be late-stage polish.

---

# 45. Testing strategy

## Ava Core

Unit tests:

- memory operations;
- context compilation;
- state revisions;
- stale patches;
- task state transitions;
- routing;
- adapter normalization.

Integration tests:

- agent task lifecycle;
- concurrent conversation;
- adapter failures;
- cancellation;
- database restart persistence.

---

## Desktop bridge

Test:

- window enumeration;
- focus tracking;
- coordinate correctness;
- UIA button lookup;
- DPI scaling;
- multi-monitor layouts.

---

## Embodiment

Test reusable scenarios:

```text
move to coordinate
look at coordinate
point at coordinate
reach target
button target inside reach
button target outside reach
monitor transition
drag/release
fall
recover
```

Use debug visualization extensively.

Display:

- target points;
- UI rectangles;
- IK targets;
- world coordinates;
- window colliders;
- navigation destinations.

---

# 46. Debugging tools to build early

Strongly consider an Ava developer overlay showing:

```text
current Ava state
active task
dialogue model
reasoning backend
state revision
foreground application
selected UI target
screen coordinates
Unity coordinates
current behaviour state
IK target
physics state
```

This will be invaluable once several systems interact.

---

# 47. Important architectural invariants

These should not be violated without a deliberate redesign.

### Invariant 1

Ava's canonical memory is external to all LLM sessions.

### Invariant 2

No reasoning backend is the central Ava runtime.

### Invariant 3

Native agent histories are working context, not truth.

### Invariant 4

LLMs do not directly control frame-by-frame embodiment.

### Invariant 5

UI Automation is preferred over visual guessing.

### Invariant 6

Vision is fallback/on-demand.

### Invariant 7

Reasoning-agent state modifications are proposed patches.

### Invariant 8

Stale agent state cannot overwrite newer canonical state.

### Invariant 9

External clients talk to Ava Core, not directly to reasoning agents.

### Invariant 10

Multiple coding agents do not freely modify the same workspace concurrently.

### Invariant 11

Physical actions and computer actions should be conceptually linked but technically separate.

Example:

```text
finger reaches button
        ↓
semantic UI action executes
```

### Invariant 12

Ava should continue functioning if any individual model/backend is unavailable.

---

# 48. Things explicitly NOT to do initially

Do not:

- build a giant monolithic application;
- couple Unity directly to Hermes/Codex;
- store identity only in prompts;
- give all agents the entire conversation history;
- continuously run a vision model;
- ask an LLM for joint positions;
- build complex ragdoll AI before basic movement works;
- build native iOS before a PWA;
- expose Ava publicly to the Internet;
- let several coding agents edit one repo simultaneously;
- spend weeks polishing the avatar before the task/state system works;
- implement autonomous computer use before basic deterministic UI interaction works.

---

# 49. Long-term possibilities

Once the architecture is stable, potential extensions include:

- proactive monitoring;
- calendar/email integration;
- notifications represented physically;
- multiple avatar forms/clients;
- different Ava embodiments across devices;
- more advanced procedural animation;
- emotion-driven pose/animation selection;
- spatial memory of applications;
- interactions with games where APIs permit;
- computer-vision-based pointing;
- task delegation visualization;
- push notifications on mobile;
- Apple Watch/other lightweight client;
- smart-home integration;
- local model fallback;
- offline mode;
- multi-user support if ever desired.

Do not build these until the core is stable.

---

# 50. Desired user experience

Ava should ultimately make interactions like these possible.

### Simple conversation

```text
User: That was an awful lap.

Ava responds immediately through the fast model.
No reasoning agent invoked.
```

### Reasoning

```text
User: Compare these two telemetry files and work out where I'm losing time.

Ava:
"I'll take a proper look."

Hermes/Sol investigates.

Ava remains responsive.

When complete, Ava presents the findings.
```

### Coding

```text
User: Can you fix that Nocturne rendering bug?

Ava delegates to Codex.

Codex works in an appropriate repository/worktree.

Ava shows optional progress.

Result is returned and reviewed.
```

### Physical desktop interaction

```text
User: Ava, pause Spotify.

Ava turns toward Spotify on monitor two,
walks across,
reaches toward the Pause button,
touches it,
and Spotify pauses.
```

### Physical attention

```text
Codex completes a task.

Ava walks toward the relevant window,
waves or calls for attention,
then points toward the changed area.
```

### Contextual assistance

```text
User, while looking at code:
"Ava, what's wrong with this?"

Ava identifies:
- active VS Code window;
- repository;
- file;
- selected lines;

and gives Codex the correct context without requiring the user to explain all of it.
```

---

# 51. Immediate development priority

The project has already been started through Hermes.

Continue the existing text-based runtime work rather than restarting unnecessarily.

The next priorities should approximately be:

```text
1. finish clean text-based Ava Core
2. validate persistent state/context architecture
3. real Hermes reasoning integration
4. Codex adapter
5. Antigravity adapter
6. routing and concurrency
7. API boundary
8. Unity desktop embodiment
9. Windows UIA perception
10. procedural physical interaction
```

Do not rush into avatar complexity before the canonical state and agent abstraction are sound.

However, design the core interfaces knowing that the Unity embodiment will eventually be an important first-class client.

---

# 52. What Astra should produce from this document

Do **not** immediately implement the entire project.

First convert this specification into a rigorous, maintainable project plan/checklist.

The output should:

1. preserve all major architectural requirements;
2. break work into phases and sub-phases;
3. identify dependencies between tasks;
4. distinguish required work from optional enhancements;
5. provide objective completion criteria for each task;
6. identify major technical risks;
7. record important architectural invariants;
8. list open design decisions without unnecessarily blocking implementation;
9. mark what is:
   - custom Ava code;
   - external library/framework;
   - external reasoning backend;
10. make the checklist suitable for updating continuously as the project develops.

Prefer hierarchical Markdown checkboxes such as:

```text
- [ ] Phase
  - [ ] subsystem
    - [ ] implementation task
    - [ ] tests
    - [ ] completion criterion
```

For every major milestone, include a clear **Definition of Done**.

Also include:

```text
Current
Next
Blocked
Later
```

or another lightweight status system.

The checklist should serve as the project's persistent engineering roadmap and should be useful to Sol/Codex/Hermes/Astra in future sessions.

Do not simplify away architectural detail merely to make the checklist shorter.

The purpose of this handoff is to preserve the intended architecture and project direction so future agents do not repeatedly reinvent or accidentally undermine it.