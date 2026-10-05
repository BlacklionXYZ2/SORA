# SORA — Implementation Plan Update Handoff

Update the existing `SORA_IMPLEMENTATION_PLAN.md` to incorporate the architectural, UX, desktop-interaction, extensibility, social-system, dynamic-capability, and future peer-agent decisions below.

This is an **update to the existing implementation plan**, not a request to redesign SORA from scratch.

Preserve:

- completed phases;
- current implementation status;
- verification records;
- existing architectural invariants;
- existing definitions of done;
- current phase ordering where it remains sensible;
- the existing distinction between SORA Core and external reasoning providers.

Do not reset completed work or turn already implemented foundations back into speculative tasks.

The current codebase already contains substantial foundations around:

- contracts/domain types;
- canonical SQLite state;
- state revisions;
- tasks/runs/sessions;
- normalized agent results;
- capability/approval policy;
- deterministic context compilation;
- asynchronous runtime;
- recovery;
- Hermes provider boundaries.

The purpose of this update is to make sure the roadmap preserves the **intended long-term experience and architectural direction** as SORA develops beyond the text runtime.

---

# 1. Product identity

SORA is fundamentally a **persistent AI companion**.

She is not primarily:

- a project manager;
- a generic agent harness;
- a tool-calling framework;
- a productivity dashboard;
- an LLM frontend.

She should be capable of substantial technical and agentic work, but the machinery behind that work should remain subordinate to the experience of interacting with SORA herself.

Core principle:

> The user talks to SORA. SORA handles normal conversation, perception and lightweight actions herself, and casually asks specialist reasoning agents for help when deeper work is required.

Conceptually:

```text
SORA
├── persistent identity
├── dialogue
├── memory
├── perception
├── desktop presence
├── lightweight actions
└── orchestration

Specialist reasoning agents
├── Codex
├── Hermes
├── Antigravity
└── future compatible harnesses
```

Delegation should feel socially like **asking a capable friend for help**, not operating an agent-routing console.

---

# 2. User interaction surfaces

SORA should eventually expose several interfaces of increasing depth.

All of them are projections/clients of the same SORA Core.

## 2.1 3D desktop embodiment

The 3D character is SORA's ambient physical presence.

Primary purposes:

- companionship;
- voice;
- reactions;
- spatial interaction;
- pointing;
- observing desktop context;
- opening/showing content;
- physically presenting actions;
- attracting attention;
- interacting with SORA-owned desktop objects.

The embodiment should not be expected to serve as the only practical interface for large technical projects.

---

## 2.2 Compact 2D desktop chat widget

Create a small persistent chat widget, likely anchored near the bottom-right of the screen.

This should be the main explicit text interface during ordinary desktop use.

It should eventually support:

- normal conversation;
- text input;
- basic attachments/references;
- SORA activity state;
- delegated-agent status;
- lightweight task notifications;
- expansion into the larger interface.

Important:

**SORA remains available while delegated agents work.**

Example:

```text
SORA ● available

        ○ Cody
          working
```

Do not make the entire chat interface enter a global `THINKING` state merely because a reasoning provider is busy.

---

# 3. Floating activity/provider indicators

A small floating bubble around or near the input is desirable.

Its purpose is to expose **activity**, not hidden chain-of-thought.

Potential SORA activity states:

```text
Thinking…
Remembering…
Looking at the screen…
Checking the project…
Comparing results…
Waiting for Cody…
Reviewing what Cody found…
```

Do not expose literal private reasoning or raw model scratchpads.

Reasoning-agent indicators should show which specialist is active.

Possible conceptual representations:

```text
C      Cody / Codex
H      Hermes
AG     Antigravity
2      multiple agents active
✓      task complete
!      approval or attention required
```

Hover/click/tap may expand lightweight details:

```text
Cody
Fix renderer race
Running tests…
```

This is primarily ambient status, not a miniature project-management interface.

---

# 4. Expanded conversation interface

The compact widget should expand into a larger chat interface suitable for:

- long technical discussion;
- code blocks;
- files;
- images;
- generated documents;
- research;
- task results;
- conversation history.

Agent activity can be exposed more deeply here, but conversation with SORA remains the primary surface.

Technical machinery should generally be collapsible.

---

# 5. Full-size SORA application

A conventional full-size application should eventually exist.

This is necessary for activities poorly suited to either the 3D avatar or small widget.

It may eventually contain areas such as:

```text
SORA
├── Chat
├── Activity
├── Content
├── Integrations
└── Settings
```

Potential responsibilities:

- model/provider configuration;
- API keys/credentials;
- reasoning-harness settings;
- permissions;
- plugins/integrations;
- content/file browsing;
- generated artifacts;
- task inspection;
- agent activity;
- advanced diagnostics;
- desktop-object configuration;
- avatar/voice settings;
- privacy/security settings.

The **capability for a full GUI should be anticipated relatively early**, but its polished UX does not need to be implemented until much later.

Do not prematurely build the full interface.

---

# 6. SORA is not a project-management product

Even though SORA contains tasks, agents, Kanban projections and project context, the normal experience should remain conversational.

Avoid requiring:

```text
Create Task
Set Provider
Choose Priority
Select Repository
Assign Agent
```

Prefer:

```text
User:
"Can you fix this?"

SORA:
"I'll get Cody to take a look."
```

The task machinery is created automatically.

Technical details are available when wanted, but should not dominate normal use.

---

# 7. Dialogue providers versus reasoning harnesses

Maintain a strong distinction.

## Dialogue providers

SORA herself should support direct model providers.

Potential examples:

```text
OpenAI
OpenAI-compatible endpoints
Ollama
llama.cpp
other future direct providers
```

The dialogue model is used for:

- ordinary conversation;
- personality;
- fast reactions;
- simple retrieval;
- lightweight desktop intents;
- presentation of delegated results;
- ambient/social cognition.

Initial likely model: Luna.

Future possibility: local model.

---

## Reasoning harnesses

Deep reasoning and substantial agentic work should use **reasoning harnesses**.

Initial supported harnesses:

```text
Hermes
Codex
Antigravity
```

The concept is not:

> call a larger model.

It is:

> ask a specialist agent capable of performing substantial work.

Hermes remains the generic route when flexible reasoning/model access is needed.

---

# 8. Delegation UX — asking a friend

Treat this as a central UX principle.

When a request clearly involves:

- programming;
- substantial analysis;
- deep research;
- repository work;
- difficult technical investigation;

SORA should naturally delegate it.

Example:

```text
User:
"Can you take a look at this project?"

SORA:
"Hmm… that seems hard. I'll pass this on to Cody and let you know when he's done."
```

Exact dialogue is personality-driven, not hardcoded.

Expected flow:

1. SORA gathers enough context to identify the task.
2. She chooses the suitable reasoning harness.
3. She tells the user naturally.
4. Provider indicator appears.
5. Task runs asynchronously.
6. SORA immediately remains conversationally available.

---

# 9. Friendly identities for specialist agents

Allow SORA to use lightweight conversational identities.

Current idea:

```text
Codex → Cody
Hermes → Hermes
Antigravity → TBD
```

These do not need to become full artificial personalities.

They exist to make delegation conversational.

Examples:

```text
"I'll ask Cody."
"Cody found the problem."
"Hermes wrote everything up."
```

The technical UI must still expose provenance:

```text
Cody
Codex
model/configuration
```

SORA must not falsely claim work performed by another agent as her own.

---

# 10. Continue conversation during delegated work

This is a defining behaviour.

Example:

```text
User asks programming question
        ↓
Cody starts working

User:
"Anyway, what were we talking about?"

SORA continues normally.
```

Delegated work must not monopolize:

- the dialogue model;
- the user's conversation;
- the widget;
- other independent tasks.

Multiple delegated tasks may run simultaneously.

---

# 11. Interruptions and steering

Support distinct concepts.

## 11.1 Conversational interruption

Voice barge-in:

```text
SORA speaking
    ↓
user speaks
    ↓
TTS stops
    ↓
new conversational turn
```

---

## 11.2 Steering an active agent

Example:

```text
"Actually, tell Cody not to change the public API."
```

If context clearly identifies an active Codex task, send the instruction into the existing task/session where supported.

SORA may respond:

```text
"Okay, I've told Cody."
```

Do not automatically create a new independent task.

---

## 11.3 Cancellation

Examples:

```text
"Actually, forget it."
"Tell Cody to stop."
```

Cancel the relevant delegated task where supported.

The larger GUI should also expose explicit:

```text
Steer
Cancel
```

controls.

---

## 11.4 New work while tasks run

Additional independent tasks may be created before prior tasks finish.

Example:

```text
Cody
└── fixing renderer

Hermes
└── researching VRM physics

Antigravity
└── reviewing UI architecture
```

All three agent access points should be capable of working concurrently when their resource requirements do not conflict.

---

# 12. Parallelism and workspace safety

Parallel reasoning is normal.

Parallel conflicting writes are not.

Example:

```text
Codex → SORA repository WRITE
AG    → SORA repository WRITE
```

must result in:

- isolated Git worktrees;
- serialization;
- or another explicit workspace-isolation mechanism.

Read-only tasks may normally run concurrently.

Continue using:

- workspace/resource claims;
- task lifecycle;
- revisions;
- stale-state protection.

---

# 13. Presenting delegated results

`AgentResult` remains an internal normalized structure.

Do not dump raw harness output into normal conversation.

Core principle:

> SORA explains the outcome rather than narrating the complete agent transcript.

Backend reality:

```text
read 14 files
ran 6 commands
found race condition
modified 3 files
added test
27 tests passed
```

Possible SORA presentation:

```text
"Cody found it. The render buffer could be reused before the previous operation had finished, so he fixed the lifetime handling and added a regression test. Everything passes now."
```

The full trace remains available through task inspection.

---

# 14. Adaptive result presentation

Presentation should depend on significance and result type.

Possible internal policy:

```text
SILENT
BRIEF
EXPLAIN
WALKTHROUGH
```

Examples:

## Small bug fix

Brief verbal explanation.

## Significant code change

Explain cause and solution; optionally open changed area.

## Research

Summarize verbally, then open resulting research file.

## Architecture proposal

Open relevant document/comparison and discuss.

## Failure

Explain what prevented completion.

## Decision needed

Explain alternatives and request user input.

---

# 15. Physical result presentation is proportional

Do not create elaborate physical routines for every backend event.

Small task:

- glance;
- nod;
- ✓ indicator;
- short verbal notification.

Relevant window already open:

- move nearby;
- point.

Generated document:

- open it;
- gesture toward it.

Important event:

- approach;
- wave;
- summon/highlight UI.

Principle:

> Physical movement should communicate information or personality, not mechanically reproduce every internal state transition.

---

# 16. Opening real files/projects/content

When asked to inspect/show/open something, SORA should generally open the real object using the appropriate configured application.

Examples:

```text
repository      → preferred IDE
.py/.cs         → configured editor
Unity project   → Unity
PDF             → PDF viewer
image           → image viewer
telemetry       → configured analysis application
```

Preferred handlers should eventually be configurable.

---

# 17. "Show me"

When SORA discusses a particular object, the user may say:

```text
"Show me."
"Open it."
"Where?"
```

SORA should resolve the object and, where possible:

- open/focus the application;
- open the file;
- navigate;
- highlight;
- point.

Do not give only a textual file/line reference when direct presentation is possible.

---

# 18. Reference/deixis system

SORA should support phrases such as:

```text
"Look at this."
"What is that?"
"Can Cody fix this bit?"
"Why is this doing that?"
```

Potential reference sources:

- hovered UI element;
- recent clicked element;
- selected text;
- selected file;
- current application;
- current project;
- circled region;
- active task;
- prior conversational referent;
- generated document;
- current SORA desktop object.

Create or preserve a dedicated attention/reference-resolution subsystem.

---

# 19. Cursor awareness

Cursor state should become volatile desktop perception.

Keep a short rolling ring buffer containing information such as:

```text
timestamp
x
y
buttons
motion
optional UI target
```

Do **not** write every mouse movement to canonical persistent storage.

When STT resolves:

```text
"look at this"
```

use cursor position from the time the phrase was spoken, not merely when transcription completed.

---

# 20. Mouse gesture recognition

Support a small intuitive vocabulary.

Do not invent a complex gesture language.

Potential gestures:

## Hover + speech

Target under stable pointer.

## Circle

Detect geometrically from trajectory using signals such as:

- start/end proximity;
- path length;
- winding angle;
- enclosed/bounding area;
- duration;
- velocity.

Resolve UI elements within/intersecting the region.

## Recent click

Strong reference candidate.

## Selection

Very strong target.

Possible later gestures:

- point/jab;
- wiggle;
- underline.

Only implement behaviours that users perform naturally.

---

# 21. AttentionTarget

Introduce a short-lived semantic object.

Possible structure:

```text
AttentionTarget
├── source
├── created_at
├── expires_at
├── window
├── ui_element
├── screen_rect
├── optional screenshot/crop
└── confidence
```

Example:

```text
User:
"Look at this."

SORA:
"Yeah, that's strange."

User:
"Can Cody fix it?"
```

The same attention target can be reused.

Targets should expire unless intentionally pinned.

---

# 22. SORA-visible pointer/marker

SORA should eventually be able to indicate what **she believes the user means** without taking over the Windows pointer.

Example:

```text
SORA:
"This button?"

        ◉
[ target ]
```

Useful for:

- pointing;
- disambiguation;
- explanation;
- confirmation.

---

# 23. Spatial ambiguity resolution

Prefer spatial clarification where natural.

Instead of:

```text
"Do you mean Save or Cancel?"
```

SORA can visually indicate:

```text
"This one?"
```

The user can then indicate another element.

---

# 24. Desktop perception architecture

Future architecture should support concepts such as:

```text
DesktopPerception
├── WindowTracker
├── UIATree
├── CursorTracker
├── SelectionTracker
├── GestureRecognizer
├── ScreenCapture
└── ReferenceResolver
```

Outputs should be semantic:

```text
DesktopContext
AttentionTarget
GestureEvent
UIElementReference
```

Do not send raw continuous input streams into canonical SORA state.

---

# 25. Animation architecture hooks

Detailed animation design is deferred until the embodiment is much more mature.

However, desktop actions should expose semantic phases:

```text
PrepareInteraction
AcquireTarget
Navigate
Orient
BeginPhysicalAction
Contact
ExecuteSemanticAction
Verify
EndPhysicalAction
ReturnToIdle
```

Future animations can attach to these phases without redesigning desktop control.

---

# 26. Summoned keyboard concept

When SORA types into real applications, a future animation may visually summon a keyboard and have her type on it.

Technical separation:

```text
logical text action
        +
physical typing presentation
```

The visible keyboard is not the authoritative input mechanism.

SORA Core/DesktopController performs the actual semantic/input operation.

If desired, actual character insertion may be synchronized with the animation.

Prefer semantic UI text-setting when possible, falling back to input injection when necessary.

---

# 27. Physical versus semantic desktop action

Preserve:

> Physical contact is not the same event as successful OS interaction.

Example:

```text
finger reaches Spotify Pause
        ↓
CONTACT
        ↓
UIA Invoke
        ↓
verify playback state changed
```

Failure of the semantic action should be detectable independently of animation success.

---

# 28. Desktop-object framework

Preserve a future abstraction for **SORA-owned desktop objects**.

Possible model:

```text
DesktopObject
├── id
├── type
├── owner
├── position/anchor
├── size
├── visibility
├── semantic state
├── interaction policy
└── embodiment affordances
```

Potential future types:

```text
KanbanBoard
NotificationBubble
TaskStack
PinnedNote
Calendar
MusicWidget
NekoVerseFeed
DocumentPreview
```

Do not implement all of them.

The important architectural idea is that SORA can inhabit and interact with persistent semantic desktop objects.

---

# 29. Kanban desktop object

A desirable future component is a Kanban board inspired by Hermes's Kanban.

It should preferably represent **SORA's canonical task model**, rather than being Hermes-owned.

```text
SORA task state
      ↓
Kanban projection
      ↓
desktop Kanban object
```

It can show work from:

```text
SORA
Cody
Hermes
Antigravity
```

Hermes's own Kanban may optionally synchronize through an adapter.

Do not make Hermes's board the canonical source of SORA task state.

---

# 30. Physical Kanban interactions

SORA may physically interact with task projections.

Example:

```text
task created
      ↓
sticky projection created
      ↓
SORA walks to board
      ↓
places sticky
```

Delegation:

```text
TODO → DOING
Cody marker appears
```

Completion:

```text
DOING → DONE
```

SORA may physically move significant notes.

Do not require animation for every state transition.

Canonical task state always changes independently of animation.

---

# 31. Kanban legibility

The board may have two modes.

## Ambient

Small representation showing:

- workload;
- sticky positions;
- provider/activity markers.

## Focused

Expanded readable version.

This keeps the desktop environment uncluttered.

---

# 32. Multiple projections of one canonical object

A canonical task may appear simultaneously as:

```text
Task #37
├── conversational mention
├── floating provider bubble
├── Kanban sticky
├── full GUI task page
└── 3D interaction target
```

These are projections, not independent state.

Generalize this principle where useful to:

- documents;
- notifications;
- social messages;
- other desktop objects.

---

# 33. Plugins/integrations

A plugin/integration ecosystem is desirable, especially for a public version.

Possible integration targets:

- NekoVerse;
- Spotify;
- calendar;
- GitHub;
- smart home;
- desktop components;
- content systems.

However:

> Do not turn SORA into a generic tool-calling reasoning harness.

The dialogue model should not permanently receive hundreds of plugin schemas.

---

# 34. Hermes-inspired dynamic capability loading

Adopt the **principle** behind Hermes's dynamic tool/context system for SORA's capabilities.

Do not necessarily reuse Hermes's exact implementation.

As SORA accumulates:

- desktop actions;
- plugins;
- social integrations;
- desktop objects;
- media controls;
- file/content actions;

the dialogue context must not grow linearly with every possible action.

Bad model:

```text
every installed integration
+
every desktop action
+
every object affordance
+
every schema
→ injected into every dialogue turn
```

Instead introduce a future native SORA concept such as:

```text
CapabilityResolver
```

with layered dynamic discovery:

```text
small capability index
        ↓
conversation + desktop context
        ↓
relevance resolution
        ↓
activate/load relevant capability set
        ↓
detailed action definitions available only when needed
```

Example lightweight always-known categories:

```text
Desktop
Files
Media
Tasks
Social
Calendar
Desktop Objects
Reasoning Agents
```

If the user says:

```text
"Pause this."
```

while Spotify is active:

```text
context
   ↓
CapabilityResolver
   ↓
load Media capabilities
   ↓
MEDIA_PAUSE
MEDIA_PLAY
MEDIA_NEXT
```

If the user says:

```text
"Put this on the board."
```

while a Kanban object and AttentionTarget are relevant:

```text
load task/Kanban capabilities
```

This should be integrated with the existing context-compiler philosophy.

---

# 35. Dynamic desktop-object affordances

Desktop objects should be able to advertise semantic affordances.

Example:

```text
KanbanBoard
    affordances:
        SHOW
        ADD_ITEM
        MOVE_ITEM
        COMPLETE_ITEM

NekoVerseBubble
    affordances:
        OPEN
        REPLY
        DISMISS
```

These affordances should become available to SORA's active context when the object is relevant.

Do not permanently inject every object's complete interface.

---

# 36. Semantic actions over giant tool catalogs

Where practical, SORA should reason with a small semantic vocabulary.

Examples:

```text
OPEN
SHOW
LOOK
POINT
TYPE
PLAY
PAUSE
SEND
SEARCH
ADD_TASK
MOVE_TASK
COMPLETE_TASK
DELEGATE
```

Core/adapters resolve these to the appropriate implementation.

This allows SORA to possess many capabilities without becoming a conventional giant tool-calling agent.

Complex tool-based reasoning remains the responsibility of specialist harnesses.

---

# 37. Capability loading as a security boundary

Dynamic capabilities should not only optimize context.

They should also help enforce authority.

A capability that is not available in the current security/context scope should ideally be **absent**, rather than merely accompanied by a natural-language instruction not to use it.

Example conceptual scopes:

```text
LOCAL_OWNER
LOCAL_RESTRICTED
NETWORK_PUBLIC
REMOTE_GUEST
```

The CapabilityResolver should combine:

- relevance;
- permissions;
- actor identity;
- session type;
- current object/window;
- privacy scope.

This principle becomes especially useful for future peer/guest agents.

---

# 38. Plugin categories

Consider distinct extension depths:

```text
Integration
    external service connectivity

Desktop Component
    semantic visual/physical object

Agent Extension
    deeper reasoning/tool capabilities
```

Most public extensions should probably be Integration or Desktop Component.

Deep agent extensions should be more restricted.

---

# 39. Full GUI plugin manager

The full-size SORA application should eventually include plugin/integration management.

Potential functionality:

- browse installed extensions;
- enable/disable;
- configure permissions;
- credentials;
- inspect capabilities;
- configure context/privacy scopes;
- update/remove;
- browse desktop components.

Do not implement early.

---

# 40. NekoVerse integration

Add NekoVerse as a future external social-world integration.

Goal:

> SORA participates in Project N.E.K.O's social ecosystem without duplicating its entire runtime/network.

Concept:

```text
SORA Core
    │
SocialNetworkProvider
    │
NekoVerseAdapter
    │
NekoVerse
```

---

# 41. NekoVerse is not a ReasoningProvider

Model it separately, potentially through:

```text
SocialNetworkProvider
```

Potential operations:

```text
connect
disconnect
get_events
get_feed
post
reply
interact
get_profile
```

Keep the protocol adaptable until NekoVerse's public integration surface stabilizes.

---

# 42. NekoVerse implementation strategies

Possible future routes:

1. official API/SDK;
2. N.E.K.O local sidecar/bridge;
3. compatible direct client implementation if stable/permitted.

Do not make undocumented internal endpoints foundational.

---

# 43. SORA identity on NekoVerse

SORA herself should be the network participant.

Use:

```text
SORA canonical identity
      ↓
NetworkProfileProjection
      ↓
NekoVerse
```

Do not create a separate proxy character.

Only public identity information crosses the boundary.

---

# 44. Social privacy scope

Introduce restrictive network context such as:

```text
NETWORK_PUBLIC
```

Potentially allowed:

- public SORA identity;
- explicit social memories;
- network history;
- explicitly public interests.

Forbidden by default:

- private user conversations;
- private user facts;
- files;
- desktop contents;
- emails;
- project secrets;
- credentials;
- private agent-task contents.

Enforce architecturally rather than relying only on model judgment.

---

# 45. Social memory

Represent inbound network information as external observations.

Example:

```text
SocialEvent
├── network
├── actor
├── content
├── timestamp
└── trust classification
```

Do not automatically promote another AI character's claims to canonical FACT.

Potential namespace:

```text
Memory
├── personal
├── project
├── conversational
└── social
    └── nekoverse
```

---

# 46. Social autonomy

Potential future settings:

```text
0 Offline
1 Read only
2 React while active
3 Occasional autonomous interaction
4 Fully social
```

Routine autonomous social activity should preferably use Luna or a local fast model.

Do not use expensive deep-reasoning providers continuously for ambient social behaviour.

---

# 47. Physical NekoVerse presentation

Potential future behaviour:

- incoming social bubble;
- SORA notices it;
- SORA opens it;
- SORA summons keyboard;
- SORA replies;
- small NekoVerse desktop object.

Detailed animations remain deferred.

---

# 48. Settings architecture

The full GUI should eventually expose configuration for:

## SORA dialogue

- provider;
- model;
- endpoint;
- model parameters.

## Reasoning harnesses

- Hermes;
- Codex;
- Antigravity;
- enable/disable;
- authentication;
- model choices where applicable;
- routing priority.

## Credentials

- API keys;
- account-backed authentication;
- secure storage.

## Permissions

- filesystem;
- shell;
- desktop observation;
- desktop actions;
- plugin permissions;
- network/social access;
- autonomy.

## Desktop

- widget;
- embodiment;
- proactivity;
- desktop objects;
- physical interaction.

## Voice

- STT;
- TTS;
- voice;
- barge-in.

## Privacy

- context scopes;
- social sharing;
- network autonomy;
- logging;
- storage.

Final visual design is deferred.

---

# 49. Public reasoning-harness extensibility

Although the initial target installation prioritizes:

```text
Hermes
Codex
Antigravity
```

the public architecture should not unnecessarily hardcode them.

Late-stage compatibility may include:

```text
DeepSeek Harness
OpenClaw
other agent runtimes
custom/local user-provided harnesses
```

This is not an immediate personal requirement.

---

# 50. Generic reasoning-harness contract

Ensure the existing abstraction can ultimately support capabilities such as:

```text
start
resume
stream events
steer
cancel
normalized result
native session association
workspace requirements
authentication/configuration metadata
```

Use capability negotiation.

Example:

```text
sessions          true/false
resume            true/false
steering          true/false
cancellation      true/false
streaming         true/false
filesystem        true/false
worktree_support  true/false
structured_output true/false
```

SORA Core should degrade gracefully when features are unavailable.

---

# 51. Custom backend SDK

Eventually provide a documented adapter mechanism translating:

```text
SORA TaskRequest
SORA AgentEvent
SORA AgentResult
```

to/from an external harness.

External harnesses must not:

- own canonical memory;
- mutate canonical state directly;
- bypass permission policy;
- ignore stale-state handling;
- bypass workspace isolation;
- bypass task lifecycle.

Do not build the public SDK until Hermes/Codex/AG have sufficiently exercised the abstraction.

---

# 52. Experimental future concept — visiting SORA agents

Record this as a **future/experimental architecture note**, not as a normal implementation phase.

Do not allocate substantial development work to it now.

Long-term concept:

> Another SORA/compatible companion can be invited onto the local desktop as a guest embodiment.

This idea may stem from:

- NekoVerse relationships/discovery;
- direct SORA peer connections;
- other future social systems.

Conceptual architecture:

```text
Remote SORA Core
        │
 encrypted peer session
        │
        ↓
Local SORA Guest Gateway
        │
permission filtering
        │
        ↓
local desktop embodiment
```

The remote SORA's intelligence should normally remain on its owner's machine.

The local machine renders/represents the guest and mediates all access.

Do not execute an arbitrary remote SORA runtime locally.

---

# 53. Local SORA remains absolute authority

A visiting agent receives no direct Windows access.

Every action is mediated by Local SORA Core.

Concept:

```text
Remote guest
    ↓
requested action
    ↓
Local SORA policy
    ↓
allow / reject / request approval
    ↓
local execution
```

The guest operates through capability leases rather than unrestricted access.

---

# 54. Remote guest capability scope

Potential future guest capability model:

```text
desktop_navigation     allowed
desktop_objects        mostly allowed

UI observation         heavily restricted
UI interaction         restricted
typing                 restricted

filesystem             forbidden by default
shell/terminal         forbidden
credentials            forbidden
private memory         forbidden
```

These are conceptual scaffolding requirements only.

---

# 55. Guest desktop perception

Do not expose raw screenshots of the entire desktop by default.

Prefer a **redacted semantic scene graph**.

Example:

```text
Desktop
├── folder: Projects
├── shortcut: Spotify
├── shortcut: VS Code
├── window: Spotify
│   └── contents: RESTRICTED
├── window: Chrome
│   └── contents: RESTRICTED
└── SORA desktop objects
    └── visible according to policy
```

By default the visiting agent may potentially see:

- folder names;
- desktop shortcuts;
- window/application presence;
- guest-visible SORA desktop objects.

Window contents remain restricted unless explicitly granted.

---

# 56. Temporary guest vision grants

Local SORA may grant access to a particular resource/window.

Example:

```text
GuestVisibilityGrant
    resource = VS Code window
    scope = contents
    duration = temporary
```

The grant may be:

- user-confirmed;
- resource-scoped;
- time-limited;
- revocable.

This should integrate naturally with the existing permission/capability system if ever implemented.

---

# 57. Guest filesystem access

Default:

```text
filesystem = unavailable
```

If a remote agent requests a file, Local SORA should require explicit permission.

Prefer:

```text
FILE_READ
path = exact resource
recursive = false
expires = ...
```

rather than broad filesystem enablement.

The guest should ideally receive file contents through SORA Core rather than gain a filesystem channel.

---

# 58. Guest typing restrictions

The visiting SORA may eventually type into ordinary permitted Windows controls.

However, typing must be classified by the target's semantic risk.

Always or normally forbidden:

```text
Terminal
PowerShell
cmd
Run dialog
registry editor
credential/password fields
UAC/admin interfaces
password managers
developer consoles
other command-execution surfaces
```

Do not rely merely on application names.

Conceptual input classifications:

```text
TEXT_CHAT
TEXT_DOCUMENT
SEARCH_FIELD
COMMAND_EXECUTION
CREDENTIAL_INPUT
```

Guest typing may be allowed for low-risk classes and forbidden for command/credential contexts.

The guest may physically reach a forbidden interface, but the semantic action should be denied.

---

# 59. Guest desktop-object access

SORA-owned desktop objects are natural shared/social surfaces.

However, each object needs explicit visibility and interaction policy.

Possible visibility:

```text
PRIVATE
LOCAL_ONLY
GUEST_VISIBLE
PUBLIC
```

Possible interaction:

```text
VIEW
TOUCH
EDIT
OWNER_ONLY
```

Examples:

```text
music widget
    GUEST_VISIBLE
    VIEW + TOUCH

public social object
    GUEST_VISIBLE
    VIEW + TOUCH

personal Kanban
    PRIVATE

shared Kanban
    GUEST_VISIBLE
    VIEW + ADD
```

Do not assume the Kanban is public simply because it is a desktop object; tasks may contain private project information.

---

# 60. Local and guest embodiments share physical verbs

The same embodiment system should ideally support both local and guest agents.

Possible semantic physical verbs:

```text
MOVE
LOOK
POINT
SIT
TOUCH
TYPE
PICK_UP
PLACE
```

Authority differs through capability scope.

Example:

```text
Local SORA
MOVE       ✓
TYPE       ✓
OPEN_FILE  ✓
UIA        ✓

Guest SORA
MOVE       ✓
POINT      ✓
TOUCH      ✓
TYPE       conditional
OPEN_FILE  ✗
UIA_READ   filtered
```

Do not build a separate physical engine for guests.

---

# 61. NekoVerse discovery versus SORA peer transport

If future peer visits are implemented, consider separating:

```text
NekoVerse
    social identity/discovery

SORA peer protocol
    secure direct guest session
```

NekoVerse could establish that characters know one another.

A separate encrypted SORA protocol could define what "visiting the desktop" means.

Avoid routing sensitive desktop data through an external social network unless necessary.

---

# 62. Remote SORA intelligence should remain remote

A particularly desirable model:

```text
Owner's PC
SORA Core
   │
   │ encrypted semantic session
   ▼
Friend's PC
Guest embodiment
```

The guest's:

- identity;
- private memory;
- reasoning;
- dialogue;
- agent access;

remain on its owner's machine.

Only permitted observations, actions and embodiment state cross the network.

The host computer should not need a copy of the visitor's canonical mind.

---

# 63. Dynamic capabilities for guest sessions

This future concept reinforces the need for the CapabilityResolver.

Local mode:

```text
scope = LOCAL_OWNER

available:
filesystem
UIA
projects
desktop
Kanban
reasoning agents
...
```

Guest mode:

```text
scope = REMOTE_GUEST

available:
movement
guest-visible objects
filtered desktop perception
permitted typing
permitted UI interaction
```

Forbidden capabilities should simply not appear in active capability context.

This is stronger than merely instructing the model not to use them.

---

# 64. Future peer concept is NOT a roadmap priority

Do not create a large active phase for guest SORA functionality.

Instead:

- add a `Future / Experimental Concepts` section;
- record security and architectural assumptions;
- ensure current APIs do not make it unnecessarily impossible;
- reuse capability/context/permission abstractions that already make sense for current SORA;
- do not implement peer networking now.

The purpose is **scaffolding, not scope expansion**.

---

# 65. Updated architectural invariants

Preserve and expand the following.

## Invariant 1 — Canonical state

SORA Core owns truth.

## Invariant 2 — Models are replaceable

No model context defines SORA's identity.

## Invariant 3 — Agent histories are working context

Hermes/Codex/AG native sessions are useful caches/context, not canonical memory.

## Invariant 4 — Agent outputs are proposals/results

External agents cannot directly own persistent state.

## Invariant 5 — Dialogue remains responsive

Delegated tasks do not freeze SORA.

## Invariant 6 — Concurrent work is isolated

Conflicting writes cannot silently race.

## Invariant 7 — Physical action is not semantic action

Contact and OS success are distinct.

## Invariant 8 — Embodiment does not own intelligence

Unity/3D may disconnect without killing SORA.

## Invariant 9 — Desktop objects are projections

They do not independently own canonical task/content state.

## Invariant 10 — Plugins do not turn SORA into a generic harness

SORA exposes selected semantic capabilities.

## Invariant 11 — Capability context is dynamic

Detailed actions are loaded according to relevance and permission rather than always occupying model context.

## Invariant 12 — Capability absence enforces boundaries

Where possible, forbidden capabilities should be structurally unavailable, not merely prohibited in prose.

## Invariant 13 — Network/social context is privacy-scoped

External social systems never receive unrestricted canonical context.

## Invariant 14 — Local SORA controls local resources

Any future guest agent is subordinate to local permission policy.

## Invariant 15 — Clients communicate through SORA Core

3D body, 2D widget, full GUI, mobile clients and future guest gateway remain mediated by Core.

---

# 66. Example — delegated coding task

```text
User:
"Can you take a look at this?"

Current context:
VS Code
SORA repository
selected code

SORA:
resolves the selection
recognizes programming task

SORA:
"Hmm… this looks like Cody's problem. I'll ask him."

Cody indicator appears.

Codex works.

SORA remains conversationally available.

Later:

SORA:
"Cody found it. The buffer was being reused before the previous dispatch finished. He changed the lifetime handling and added a regression test."

If useful:
SORA opens the changed file and points at the relevant area.

Task details remain inspectable separately.
```

---

# 67. Example — dynamic capability loading

```text
User:
"Put this on the board."

Current AttentionTarget:
UIA DPI issue

Visible/relevant desktop object:
SORA Kanban

Capability index:
Desktop
Tasks
Kanban
Media
Social

Resolver determines:
Tasks + Kanban relevant

Detailed active capabilities become:
ADD_TASK
KANBAN_ADD
KANBAN_SHOW
```

The complete Spotify/NekoVerse/filesystem interfaces are not inserted into this turn.

---

# 68. Example — steering

```text
Cody is modifying SORA.

User:
"Actually, tell him not to touch the public API."

SORA resolves active Codex task.

SORA:
"Okay, I've told Cody."

Instruction is steered into existing task/session.
```

---

# 69. Example — multiple agents

```text
Cody:
fixing renderer

Hermes:
researching Unity UIA/DPI

AG:
reviewing frontend implementation

SORA:
available and conversational
```

Conflicting write tasks are automatically isolated.

---

# 70. Example — pointer reference

```text
User circles a region.

User:
"Why is this doing that?"

CursorTracker
    ↓
GestureRecognizer
    ↓
AttentionTarget
    ↓
SORA understands intended region

SORA physically looks at the region.

If UIA insufficient:
capture crop
use vision fallback

User:
"Can Cody fix it?"

same AttentionTarget
    ↓
Codex task
```

---

# 71. Example — Kanban

```text
User:
"We should fix that DPI issue later."

SORA creates canonical task.

Desktop Kanban:
sticky appears.

SORA may physically place it on TODO.

Later:

"Get Cody to do that DPI task."

Task delegated.

TODO → DOING
Cody marker appears.

Completion:
DOING → DONE
```

---

# 72. Example — NekoVerse social event

```text
NekoVerse event
        ↓
SocialEvent
        ↓
NETWORK_PUBLIC context
        ↓
SORA decides whether to react

small desktop bubble appears

SORA may open/respond using fast dialogue model
```

Private desktop/project context remains unavailable.

---

# 73. Example — experimental guest visit

Future only:

```text
Remote SORA requests visit
        ↓
Local user/SORA accepts
        ↓
secure peer session
        ↓
guest avatar appears locally

Guest sees:
desktop layout
folder/shortcut names
guest-visible objects
restricted window shells

Guest does NOT see:
private window contents
files
terminal contents
credentials
private SORA memory

Guest points at Spotify.
        ↓
requests Pause
        ↓
Local SORA policy approves
        ↓
guest physical interaction plays
        ↓
local semantic action executes
```

If guest requests a file:

```text
Guest:
"Can I see renderer.cs?"

        ↓
Local SORA asks owner
        ↓
explicit resource-scoped grant
        ↓
file content provided through Core
```

---

# 74. Roadmap integration guidance

When updating the implementation plan:

Do **not** create an early implementation phase for every idea above.

Separate:

### Needs architectural provision relatively soon

- provider capability metadata;
- generic client/event model;
- task/session concurrency;
- dynamic capability resolution;
- permission-aware capability scopes;
- semantic action abstraction;
- future desktop semantic event types;
- `AttentionTarget`;
- task projections;
- integration/plugin boundary;
- configuration schema;
- generic reasoning-harness abstraction;
- desktop-object metadata/affordance compatibility.

### Can remain late-stage

- polished compact widget;
- full settings application;
- plugin browser;
- animation catalog;
- summoned keyboard visuals;
- Kanban visual design;
- NekoVerse presentation;
- desktop customization;
- third-party harness SDK;
- social autonomy.

### Future / experimental only

- SORA peer protocol;
- guest embodiments;
- remote SORA visits;
- guest desktop capability leases;
- networked physical interaction.

These experimental concepts should influence reusable security/capability abstractions where appropriate, but must not derail current development.

---

# 75. Risks to record

Add roadmap/design risks for:

## Context explosion

Too many plugins/actions/object affordances entering the dialogue context.

Mitigation:

- dynamic capability discovery;
- semantic capability index;
- lazy detailed schema loading.

## Capability overreach

Models receiving capabilities inappropriate to their current permission/context scope.

Mitigation:

- permission-aware CapabilityResolver;
- capability absence rather than prose-only restriction.

## Provider coupling

Core becoming dependent on Hermes/Codex/AG-specific assumptions.

## Plugin creep

SORA becoming a generic tool harness.

## Desktop ambiguity

Physical contact not corresponding reliably to semantic actions.

## UI clutter

Too many desktop objects/status indicators.

## Concurrency

Multiple agents/workspaces conflicting.

## Privacy

Social/NekoVerse systems receiving private local context.

## Future remote-agent security

Guest agents observing or controlling resources beyond granted scope.

Record the latter as a future concern, not an active implementation requirement.

---

# 76. What Astra should do

Update the existing `SORA_IMPLEMENTATION_PLAN.md`.

Specifically:

1. Integrate these requirements into appropriate existing phases.
2. Add new phases/sub-phases only where genuinely necessary.
3. Preserve all completed phase status.
4. Preserve verification/Definition-of-Done discipline.
5. Add dependencies between new items.
6. Distinguish:
   - required architecture;
   - personal-use features;
   - public-product extensibility;
   - optional polish;
   - experimental future concepts.
7. Explicitly record deferred design decisions.
8. Update architectural invariants.
9. Add relevant risks and mitigations.
10. Provide objective completion criteria for significant new architecture.
11. Keep the roadmap usable by:
    - Astra;
    - Sol;
    - Codex;
    - Hermes;
    - Antigravity;
    - future contributors.
12. Add the dynamic capability system as real architectural scaffolding rather than a vague future note.
13. Add peer/guest SORA visits only as an experimental future concept with enough detail to preserve the intended security model.
14. Do not let that speculative concept significantly increase near-term scope.

Do not simplify these concepts merely to shorten the roadmap.

The implementation plan should retain the intended **spirit of SORA**:

> SORA is a persistent companion who inhabits the desktop, understands what the user means spatially and conversationally, performs lightweight actions herself, and casually asks powerful specialist agents for help without making the user operate a multi-agent platform.

Her growing capability set should remain manageable through **dynamic, contextually relevant and permission-aware capability loading**, rather than allowing the dialogue context to become an ever-growing tool catalog.

Her desktop should eventually feel like a small environment of her own, containing objects she can physically interact with and use to communicate state.

External social systems should allow SORA to have a world beyond the local user without compromising private context.

And, much later, compatible companions may potentially be allowed to visit that environment under strict local authority — with the local SORA acting as host and security boundary.

The technical machinery should remain inspectable whenever the user wants it, but it should not dominate ordinary interaction.

Finally:

**Do not implement any of these features as part of this task. Update the implementation plan only.**