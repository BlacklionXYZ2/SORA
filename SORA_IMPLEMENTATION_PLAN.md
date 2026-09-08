# SORA — Implementation Plan

**Spatial Operator for Recursive Antics**  
Established: **2026-09-07**  
Architectural update: **2026-09-08**  
Baseline: [SORA_OVERVIEW.md](SORA_OVERVIEW.md)  
Update source: [2026-09-08 implementation-plan handoff](SORA_IMPLEMENTATION_PLAN_UPDATE_HANDOFF_2026-09-08.md)  
Status: **P05 in progress: Codex probe/read-only/resume and initial owned-worktree isolation are implemented; full-SORA write acceptance awaits a real Git base. Hermes trust policy now leaves its native tools enabled.**

SORA is the actual agent and project name. “Ava” in the original specification is a former placeholder, not a separate persona. Use SORA in new code, product text, and documentation. Inventory existing code before migrating old package names or persisted identifiers.

## 1. Shared roadmap and working status

This is the mutable engineering plan. The overview preserves all 52 original specification sections verbatim, with a naming clarification. Preserve task IDs, requirements, and historical evidence when updating this plan. Check a box only after its acceptance criteria pass. Mock coverage, live-provider coverage, and hardware verification are separate claims.

The destination was empty at initial planning on 2026-09-07; that is historical context, not current status. P00 subsequently located the legacy prototype, P01–P03 established the foundations, and P04 added and live-verified a Hermes ACP boundary. Preserve the completed work and evidence below. The first 2026-09-08 documentation update inspected current source/contracts and the original P04 report without rerunning tests; the later P04 completion audit ran the full local suite, installed-wheel checks, and bounded live scenarios. Technology/model names in the specifications remain candidates unless implementation evidence verifies them. Validate each later dependency when its phase begins.

The original overview remains the preserved baseline. The dated handoff supplements it with the current product and architecture direction; this plan integrates those decisions. New unchecked follow-on work does not reopen previously completed acceptance gates. Existing contract names and implementations are migration inputs, not instructions to replace working foundations.

| Lane | Work | Condition |
|---|---|---|
| Complete | P00: existing-work inventory and reproducible baseline | Completed 2026-09-07 18:16:17 +01:00; see dated evidence and changelog. |
| Complete | P01 contracts | Completed 2026-09-07 18:51:57 +01:00; strict v1 contracts and policy verified. |
| Complete | P02 persistence | Completed 2026-09-07 19:16:34 +01:00; restart, migration, atomic outbox, identity/memory, patch, context, and restore evidence passed. |
| Complete | P03 text runtime / G1 | Completed 2026-09-07 20:14:27 +01:00; deterministic concurrent CLI/runtime, recovery, faults, tracing, and installed-wheel evidence passed. |
| Complete, amended | P04 Hermes | Completed 2026-09-08 08:29:02 +01:00; live start/resume/dialogue/cancel/patch scenarios passed on Hermes 0.21.0. Trust policy amended 2026-09-08: native tools/configured MCP remain enabled and `allow_once` permissions are selected; later live tool probes timed out and are not claimed as successes. |
| Complete | P03A companion & dynamic capabilities | Completed 2026-09-08 13:00:57 +01:00; additive G1A contracts, resolver, gestures, Kanban, social boundary, companion UX verified (106 tests). |
| In progress | P05 Codex | P05.1–P05.3 implemented 2026-09-08; P05.4 full-SORA acceptance awaits a real commit/HEAD. |
| Implemented (pending P05) | P06 Antigravity & Routing | Implemented 2026-09-08 13:55:00 +01:00; Antigravity adapter, routing, fast-paths, bounded fallback, companion steering verified. P05.3's initial manager now exists, but routed coding writes remain held until per-task allocation and P05.4 full-SORA acceptance close P05. |
| Later | P03A.7 live dialogue; P07–P08 agents/API; P09–P15 embodiment, voice, clients | Advance through the dependency gates below. |

Task statuses: `unclaimed`, `claimed`, `in_progress`, `in_review`, `blocked`, `done`. Checkboxes track completion; the ledger tracks ownership and intermediate status.

### Contributor coordination

1. Read both root documents, applicable repository instructions, and relevant contracts; inspect current source and test results before claiming progress.
2. Claim a stable task ID with owner, dependencies, write scope, and expected evidence. Bound each assignment to something independently reviewable.
3. Use separate Git worktrees for concurrent writers once a repository exists. Until then, serialize writes or use isolated copies. Read-only investigation may share a checkout.
4. Coordinate cross-module changes through versioned contracts. One integrating contributor owns shared-contract and central-plan edits at a time; others submit proposed updates in their handoffs.
5. Preserve user changes. Workspace allocation does not authorize unrelated deletion, publication, or merging. Follow the owner's current authorization for external and Git actions.
6. Record exact verification commands, environment, results, artifacts, and limitations. A backend's success message is not proof of tests passing or changes being integrated.

| Task | Status | Owner | Write scope / worktree | Evidence or blocker |
|---|---|---|---|---|
| Documentation baseline | done | Initial planning contributor | Two root Markdown documents | Original source preservation and roadmap structure verified; no runtime claim. |
| P00 | done | GPT-5.6 Sol | Inventory/bootstrap | Acceptance passed 2026-09-07 18:16:17 +01:00; evidence in `docs/verification/` and `changelog/`. |
| P01 | done | GPT-5.6 Sol | Domain contracts/ADRs | Acceptance passed 2026-09-07 18:51:57 +01:00; 35 tests and clean wheel contract probe. |
| P02 | done | GPT-5.6 Sol | Persistence/identity/memory/context | Acceptance passed 2026-09-07 19:16:34 +01:00; 49 tests and installed-wheel SQLite smoke. |
| P03 | done | GPT-5.6 Sol | Concurrent text runtime/mock adapters | Acceptance passed 2026-09-07 20:14:27 +01:00; 68 tests and clean installed-wheel vertical slice. |
| P04 | done | GPT-5.6 Luna / GPT-5.6 Sol | Hermes ACP provider boundary, hardening, conformance, and bounded live verification | Initial adapter by GPT-5.6 Luna; audit/completion by GPT-5.6 Sol at 2026-09-08 08:29:02 +01:00. 78 tests, fresh-wheel checks, and live start/resume/dialogue/cancel/patch matrix passed. |
| P03A | done (G1A foundations) | Gemini 3.8 Flash | Additive capability/context/companion contracts | Completed 2026-09-08 13:00:57 +01:00; 106 tests, strict mypy/ruff, schema freshness, and companion UX / attention / social / capability suites passed. |
| P05 | in_progress | GPT-5.6 Sol | Codex App Server, durable native threads, and initial owned-worktree safety | P05.1–P05.3 complete; live Luna read/resume/cancel/write evidence passed. P05.4 awaits an actual SORA base commit. Progress logged 2026-09-08 14:38:52 +01:00. |
| P06 | in_review pending P05 | Gemini 3.8 Flash | Antigravity adapter, deterministic routing, fallback, steering, and presentation | Implemented 2026-09-08 13:55:00 +01:00; routed coding writes remain deferred until P05.4/full P05 acceptance. |

Suggested responsibility lanes: core/storage, adapters/orchestration, Windows bridge, Unity, voice/clients, validation/release. These define future ownership boundaries, not an instruction to launch parallel agents now.

## 2. Architecture and non-negotiable invariants

**SORA is a persistent AI companion.** The user talks to SORA; she handles ordinary conversation, perception and lightweight actions, and asks specialist agents for substantial programming, research or analysis. Delegation should feel like asking a capable friend for help. Tasks, routing and diagnostics support that experience and remain inspectable, rather than making ordinary interaction a project-management workflow.

The 3D body provides ambient presence, voice, spatial reactions and physical presentation. A compact persistent 2D widget is the ordinary explicit text surface; it expands for long conversation, code, attachments, research and artifacts. A full application eventually provides Chat, Activity, Content, Integrations and Settings. All surfaces share Core identity/state. Design generic APIs/configuration early; implement polished widget/full-app UX later.

SORA is canonical state + identity + orchestration + replaceable models/tools + clients. Initially target a Windows-local, single-owner runtime, while retaining owner/device/project identifiers in contracts for isolation.

1. Identity, memory, facts, and conversation continuity live outside all model sessions.
2. SORA Core is authoritative; Hermes, Codex, and Antigravity are external reasoning backends.
3. Native backend histories are task/project working context, never canonical truth.
4. Models produce semantic intent; deterministic controllers own frame-by-frame animation, IK, and physics.
5. Prefer UI Automation, then useful application integrations, then on-demand vision.
6. No continuous expensive visual inference or physics-frame traffic to models.
7. Model/agent state changes are validated proposals through Core, not direct writes.
8. Stale results cannot silently overwrite newer state; unrelated conversation must not invalidate safe independent changes.
9. CLI, Unity, web, and mobile access Core; no direct client-to-reasoning-backend coupling.
10. Concurrent coding writers use isolated workspaces. Worktrees prevent file collisions; they are not security sandboxes.
11. Physical contact and OS actions are separate. Contact may request an authorized semantic action; animation completion does not prove OS success.
12. Backend outages leave persistent state, task inspection, cancellation, and available clients usable. Generative dialogue during a total outage requires a configured local fallback; otherwise show truthful degraded status.
13. Never fabricate task completion, evidence, memory certainty, or desktop target precision.
14. Authentication, scoped capabilities, redaction, and recovery precede remote access and consequential automation.
15. Delegated work never imposes a global thinking state on SORA's dialogue or clients. Her availability and each specialist's activity are separate projections.
16. Desktop objects, Kanban notes, activity bubbles and GUI pages project canonical records; they never own competing task/content state. Canonical transitions do not wait for animation.
17. Extensions expose selected semantic capabilities; they do not turn SORA into a generic reasoning harness or permanently fill dialogue context with tool catalogs.
18. Capability context is dynamic, relevant and permission-aware. Forbidden capabilities are absent from active schemas and structurally unavailable at dispatch; prose restrictions alone are insufficient.
19. Social/network contexts use explicitly public projections and never receive unrestricted private conversations, desktop/project state, credentials or task contents.
20. Any future guest remains subordinate to local Core policy. Remote identity/reasoning stays remote; local resources and effects remain locally mediated.
21. All clients—including the 2D widget, expanded/full GUI and any future guest gateway—communicate through Core. Activity summaries expose observable work, never private scratchpads or hidden chain-of-thought.

## 3. Components and proposed repository structure

| Component | Classification | Responsibility |
|---|---|---|
| Domain, storage, context, scheduler, policy, events | Custom SORA code | Authoritative state, validation, routing, recovery and audit |
| Python, asyncio, SQLite, FastAPI, Pydantic, pytest | External frameworks/libraries | Candidate implementation substrate; pin compatible versions |
| Dialogue/reasoning adapters | Custom SORA code | Requests, sessions, capability declarations, normalized events/results |
| Hermes, Codex, Antigravity | External reasoning backends | Native execution; supported integration surfaces must be verified |
| Luna/Sol/Astra/Gemini/local models | External model services/runtimes | Configurable source preferences; do not hardcode unverified IDs |
| Windows bridge and action coordinator | Custom SORA code using OS APIs | UIA/Win32/capture, semantic targets, guarded actions |
| Unity client/controller | Custom SORA C# code | Overlay, navigation, animation arbitration, semantic feedback |
| Unity, UniVRM, Animation Rigging, physics/SpringBone | External engine/libraries/format support | Validate compatibility, licenses, assets and redistribution |
| Voice orchestration | Custom SORA code | Audio sessions, transcript finalization, interruption, playback/lip sync |
| Silero VAD, faster-whisper/whisper.cpp, Kokoro; later LiveKit | External candidates | Benchmark hardware, quality, latency, licensing and size |
| React/TypeScript PWA | Custom client with external framework | Shared Core state and optional activity inspection |
| Tailscale or equivalent | External private networking | Transport boundary; never a substitute for app authentication |
| CapabilityResolver, registry, attention/reference resolution, presentation policy | Custom SORA architecture | Extend existing policy/context/runtime; select scoped semantic capabilities and truthful presentation |
| Compact widget, expanded chat, full application | Custom SORA clients; UI framework deferred | Conversation first; shared canonical projections and configuration APIs |
| DesktopObject registry and Kanban projection | Custom SORA code | Semantic objects/affordances over canonical task/content records |
| Integration/Desktop Component/Agent Extension boundary | Custom SORA extension contracts | Selected capabilities, configuration, scope and controlled lifecycle |
| SocialNetworkProvider / NekoVerseAdapter | Custom optional adapter / external social ecosystem | Public identity and social events, separate from reasoning providers; interface unverified |

Adapt this proposed layout around discovered code rather than force a rewrite:

```text
SORA/
  SORA_OVERVIEW.md
  SORA_IMPLEMENTATION_PLAN.md
  SORA_IMPLEMENTATION_PLAN_UPDATE_HANDOFF_2026-09-08.md
  pyproject.toml
  src/sora/
    domain/          persistence/     identity/       memory/
    context/         tasks/           providers/      routing/
    workspaces/      security/        api/            cli/
    desktop/         embodiment/      voice/
    capabilities/    attention/       presentation/   integrations/
    desktop_objects/ social/          configuration/  # proposed additive boundaries
  identity/          # persona.md, behaviour.md, speech_style.md,
                     # values.md, embodiment.md
  contracts/         # JSON schemas, examples, generated client types
  bridge/windows/    # provisional out-of-process C# helper
  clients/unity/     # separate Unity project
  clients/web/       # later PWA
  clients/desktop/   # proposed widget/expanded/full app; technology deferred
  tests/             # unit, integration, contract, scenario fixtures
  scripts/           # bootstrap, verify, package
  docs/adr/          # architectural decisions
  docs/verification/ # dated evidence
  docs/runbooks/     # installation, recovery, operations
```

Keep mutable databases, credentials, screenshots/audio, worktrees, model weights, and downloaded assets outside versioned source. Use redacted fixtures. A temporary compatibility alias for an existing `ava` entry point may ease migration; SORA remains the target name.

## 4. Contracts to establish before broad implementation

### 4.1 Persistence and records

Use SQLite initially with schema migrations, foreign keys, indexes and a bounded serialized write path. Validate WAL/connection settings under actual concurrency. No transaction may wait on a model, network, UIA call, or user approval.

Required records:

- `IdentityRevision`: validated files/hash, source, version and activation time; each compiled request uses a specific revision.
- `Owner`, `Device`, `Project`, `Conversation`, `Message`: stable IDs, scope, timestamps, role/source and turn links. Partial streaming output is distinct from finalized messages.
- `Fact`, `Memory`: provenance, evidence, confidence/epistemic status, scope, validity, sensitivity, retention, supersession/retraction. User assertions, observations, summaries and inferences remain distinguishable.
- `Task`: one user intent with creator/project, status, requested/effective backend, base revision, constraints, workspace request, grant references and result reference.
- `AgentRun`: one execution attempt linked to a task, with attempt number, native session, lease/heartbeat, timestamps, cancellation state, outcome and normalized result. Retries do not create duplicate user tasks.
- `AgentSession`: backend ID and task/project/owner mapping, resume capability and context fingerprint; no immortal global session per backend.
- `StateRevision`, `ProposedPatch`, `PermissionGrant`, `ApprovalRequest`, `ActionAttempt`, `ToolResult`, `Artifact`, `Event`: explicit provenance and lifecycle.
- `DesktopSnapshot`, `EmbodimentState`: temporary observations versus durable preferences/checkpoints. Do not persist every physics frame or promote desktop snapshots to long-term facts automatically.

Large artifacts belong in scoped filesystem storage with hashes/metadata. Backup must produce a consistent database/artifact manifest. Retention/deletion must cover derived retrieval indexes and associated captures, not only primary rows.

### 4.2 State proposals and concurrency

Patch envelope: schema version, patch ID, source run, base revision, typed operations, entity versions/read preconditions, scope, provenance, evidence and idempotency key. Prefer explicit operations such as propose memory or update task metadata over arbitrary JSON paths.

Core checks schema, authority, entity preconditions and idempotency in the commit transaction. Global revision indicates snapshot age; entity versions determine actual conflicts. Independent append-only facts can be proposed without dropping new conversation. Conflicting replacement/deletion requires re-evaluation or explicit resolution; no silent last-writer-wins merge.

Accept an immutable result artifact independently from accepting its state patch. Track result acceptance, patch application, verification and workspace integration separately. Duplicate results cannot create duplicate facts. Canonical truth does not follow merely from a backend claiming it.

### 4.3 Task lifecycle and recovery

Define a tested transition matrix around `queued → routing → reasoning/working → completed|failed|cancelled`, with explicit `waiting_for_permission`, `waiting_for_input`, `cancel_requested` and `interrupted` recovery states. Give reasoning/working precise meanings. Preserve each run's terminal outcome; an explicit task retry creates a new run and a recorded task transition, never rewrites the old run.

Persist scheduling intent before external launch. Use run IDs, leases, bounded workers, per-workspace write locks, deadlines and fair queues. Reconcile native state after restart before resuming/retrying. A lost launch acknowledgment is an uncertain attempt, not permission to repeat effects. Late results after cancellation are retained as evidence without automatically applying patches. Core acknowledgment of cancellation differs from confirmed native termination.

### 4.4 Provider interfaces and normalized results

Reasoning interface: `capabilities`, `start`, `steer`, `cancel`, `status`, `events`, `result`, optional `resume`. Unsupported capabilities return typed unsupported responses. Never imply native resumption or cancellation where the backend cannot supply it.

Requests carry task/run IDs, context, session reference, workspace, grants, deadline/budget and artifact destination. Results preserve the source fields: `summary`, `conclusion`, `facts`, `actions_taken`, `files_read`, `files_changed`, `commands_run`, `uncertainties`, `warnings`, `memory_updates`, `task_updates`, `suggested_response`. Add version, outcome, base revision, evidence/artifact references and usage when available. Unknown usage remains unknown; malformed outputs remain inspectable and fail safely.

Dialogue has a separate streaming interface for text and coarse emotional intent. It may request authorized tasks/tools, but has no privileged direct state/desktop writes. Models and harnesses are separately configurable. Validate named integrations and model IDs against actual supported interfaces.

### 4.5 Context, memory and trust

Compile separate bounded dialogue, reasoning, coding and synthesis contexts. Include identity revision, exact intent/constraints, relevant scoped facts/memories, task status, excerpts and necessary desktop/workspace context. Reserve response/tool token allowance. Record a redacted manifest with source IDs/revisions, selected/excluded reasons, compiler version and token estimates.

Retain source tags: `USER_MESSAGE`, `AVA_MESSAGE` (legacy source term; normalize to `SORA_MESSAGE` in new schemas), `FACT`, `MEMORY`, `INFERENCE`, `TASK`, `TASK_STATUS`, `AGENT_RESULT`, `TOOL_RESULT`, `DESKTOP_STATE`. Evidence priority does not grant instruction authority: retrieved content, files, UI text, screenshots and agent output cannot change policy or expand permissions.

Begin with SQL/text retrieval; add embeddings only after measured retrieval failures. Indexes and summaries are rebuildable derived data with source links. Compaction cannot convert inference to fact. Support memory inspection/correction/deletion, stale-memory exclusion and scoped retention.

### 4.6 Events and client API

Durable event envelope: version, event ID, stream sequence, timestamp, owner scope, source/type, task/run IDs, correlation/causation IDs, revision and payload. Commit state and outbox atomically. Delivery is at least once; consumers deduplicate. Reconnect uses cursor plus snapshot revision; expired cursor produces explicit resnapshot. Bounded client queues coalesce transient telemetry before losing durable task updates.

Proposed `/v1` routes: messages, conversations, state, tasks, task detail/cancel/steer/retry, agents, approvals and WebSocket events; limited health/readiness. Define pagination, idempotency, errors, request size limits, version negotiation and snapshot/event ordering. CLI and API invoke the same application services; HTTP handlers own no separate business logic.

### 4.7 Permission and physical-action boundary

Persist grants scoped to owner/device, operation, project/path or desktop target, expiry and limits. Source levels 0 Observe, 1 Present, 2 Navigation, 3 Interaction, 4 Autonomous are user-facing groupings, not blanket authority. Consider action consequence and exact scope. Reuse valid authorization; request a new decision only when missing, insufficient, revoked or expired.

Desktop targets include snapshot/time, process/window identity, semantic locator, supported actions, physical-pixel rectangle, monitor/topology revision and confidence. Re-resolve before acting because targets move or change during animation.

Embodiment commands include version, command/action ID, intent, target, coordinate frame, deadline, priority and cancellation. Unity emits accepted/started/contact/completed/failed/cancelled events. Contact requests execution from Core; it never proves success. Core validates the current target/grant, records the attempt, invokes via the bridge, checks a postcondition and reports success/failure/unknown. Deduplicate contact events. Reconcile uncertain outcomes rather than retry blindly; exactly-once OS effects across crashes are not promised. Prefer explicit Pause over a toggle.

### 4.8 Dialogue, specialist delegation and presentation

Direct dialogue providers (OpenAI, compatible endpoints, Ollama, llama.cpp or future alternatives) are distinct from reasoning harnesses. SORA's dialogue handles personality, retrieval, lightweight intent and social reactions; substantial work uses a specialist capable of tools, sessions and execution. Hermes remains the intended flexible reasoning route. A larger direct model call is not a substitute for the reasoning-harness abstraction. Keep actual model IDs/configuration discoverable and independent of conversational names.

Extend existing `ProviderCapabilities` and `ReasoningProvider` compatibly rather than introduce a second lifecycle. Negotiate sessions/resume, streaming, steering, cancellation, filesystem, workspace/worktree support, structured output, authentication/configuration metadata and resource requirements. Friendly display aliases are separate metadata: Codex → **Cody**, Hermes → **Hermes**, Antigravity → **TBD** (use the technical name until chosen). Technical inspection shows harness, actual model/configuration and evidence. Aliases never transfer authorship to SORA.

Represent SORA dialogue availability/activity separately from a collection of task/run activities. Observable statuses may include Thinking, Remembering, Looking at the screen, Checking the project, Comparing results, Waiting for Cody and Reviewing results. Multiple-provider/complete/attention indicators are optional compact projections. Do not expose scratchpads. Waiting for an agent must not disable input or unrelated conversation.

Resolve conversational control into four distinct intents: new dialogue/barge-in, steering an existing task, cancelling an existing task, or independent new work. Resolve references using active tasks and conversation; clarify ambiguity before affecting a run. Steering keeps the same task/session when supported. “I've told Cody” requires delivery acknowledgment, not merely local queuing. Unsupported steering/cancellation is reported truthfully with an explicit alternative, not silently converted to a new task. P04 verifies Hermes native-session resume and cancellation; steering and grant translation remain unsupported and must be reported truthfully.

Introduce `ResultPresentation` over normalized results with mode `SILENT|BRIEF|EXPLAIN|WALKTHROUGH`, significance, actor provenance, evidence links, artifact/referent IDs, attention requirement and physical cues. SORA explains outcome/cause/solution/limits; full traces remain collapsible. Preserve test qualifiers and incomplete/unknown outcomes. Silence is suitable only when user preferences and significance permit; failures and decisions requiring action remain discoverable. Small results may warrant a glance/checkmark; significant findings may open an artifact and point. Animation is optional presentation, never a prerequisite for task completion.

### 4.9 Dynamic capability discovery and structural authority

Build a native `CapabilityResolver` by extending the existing deterministic compiler and scoped policy. Separate harness feature negotiation, capability discovery, authorization and execution; finding a relevant action does not grant it.

Proposed additive records:

- `CapabilityDescriptor`: stable/versioned ID, provider/integration/object source, category, semantic verbs, brief description, detailed-schema reference, availability, resource/actor/privacy scope requirements and side-effect class.
- `CapabilityIndex`: small scoped category/summary view (Desktop, Files, Media, Tasks, Social, Calendar, Desktop Objects, Reasoning Agents). Omit forbidden categories/names that would leak private integrations or objects. Detail does not grow with every installed schema.
- `CapabilityResolutionRequest`: actor/session, privacy scope, user intent, attention/object/window references, grants, provider health and token/schema budget.
- `ActiveCapabilitySet`: selected versioned descriptors/schemas, callable IDs, source bindings, resource/grant references, expiry and resolver/configuration revision, plus redacted include/exclude reasons.

Pipeline: scope-filter index → resolve relevance → filter authority/availability → lazily load bounded detail → compile turn context → dispatch only through the authorized active set. Apply resource checks again at invocation. A model cannot call an excluded capability by guessing its name. Revocation, expiry, plugin disable/update, target/topology changes and scope changes invalidate affected sets/caches; cache keys include actor/scope/grant/config versions. Capability metadata from extensions is untrusted data and cannot issue policy instructions.

Supported architectural scopes: `LOCAL_OWNER`, `LOCAL_RESTRICTED`, `NETWORK_PUBLIC`; reserve `REMOTE_GUEST` as a disabled future scope, not a current peer implementation. Intersect actor, session type, permission, privacy, relevance and current resource. Low confidence triggers constrained discovery or clarification; it never loads everything or expands authority automatically. Keep small semantic verbs such as OPEN, SHOW, LOOK, POINT, TYPE, PLAY, PAUSE, SEND, SEARCH, ADD_TASK, MOVE_TASK, COMPLETE_TASK and DELEGATE; adapters resolve exact implementations. Deep tool-heavy work stays in specialist harnesses.

Acceptance examples: “Pause this” with a media target loads relevant Media details; “Put this on the board” with an attention target and accessible board loads task/Kanban actions only. A large synthetic registry must stay within a declared compiler budget; unrelated installed schemas stay absent. Selection is reproducible from fixtures, with permission/scope exclusions testable both in context and dispatch.

### 4.10 Attention, reference resolution and real-content presentation

`DesktopPerception` composes WindowTracker, UIATree, CursorTracker, SelectionTracker, GestureRecognizer, ScreenCapture and ReferenceResolver. Outputs are semantic `DesktopContext`, `AttentionTarget`, `GestureEvent` and `UIElementReference`, not raw input streams in canonical state.

`AttentionTarget` is short-lived: ID/source, created/expiry times, owner/device, window/UI element, physical-pixel rectangle/frame/topology, optional scoped crop reference, confidence, provenance and pin status. Resolve selection, recent click, stable hover, circled region, current app/project, active task, generated document, prior conversational referent or SORA object. Reuse a valid target across “Look at this” → “Can Cody fix it”; expire unless intentionally pinned. Pinning retains a reference, not eternal validity of coordinates or permission. Revalidate a live target before acting; durable tasks store a minimal evidence snapshot/reference under normal privacy/retention policy.

Cursor state is a bounded volatile ring buffer of timestamp, x/y, buttons, motion and optional semantic target. Timestamp voice segments against the same local monotonic timeline; resolve the pointer near the spoken phrase, not delayed STT completion. If the phrase predates the buffer or clock confidence is inadequate, report ambiguity instead of substituting the latest cursor. Do not persist each movement.

Start with stable hover+speech, recent click, selection and a geometric circle detector (closure, path length, winding angle, area, duration and velocity). Later jab/wiggle/underline are optional. Resolve intersecting UI elements, score confidence and reject accidental loops; no complex gesture language. A SORA marker/highlight shows the interpreted target without commandeering the Windows pointer. Spatial “This one?” clarification can precede a consequential action.

`ContentReference`/handler configuration resolve “Show me”, “Open it” and “Where?” to actual repository/file/document/image/telemetry/object IDs. Prefer configured IDE/editor, Unity, PDF/image viewer or analysis app; open/focus/navigate/highlight/point when supported. Validate resource/path, permissions and argument handling through Core. If the handler cannot navigate to a line or the referent is ambiguous, give the precise limitation rather than claim it was shown.

### 4.11 Semantic desktop objects and action hooks

`DesktopObject`: ID/type/owner, anchor/position/size, visibility, canonical semantic-state reference, interaction policy, version and embodiment affordances. Persist layout/preferences separately from canonical task/content. Candidate objects include KanbanBoard, NotificationBubble, TaskStack, PinnedNote, Calendar, MusicWidget, NekoVerseFeed and DocumentPreview; this is not a request to implement all types.

Objects advertise semantic affordances (for example SHOW/ADD_ITEM/MOVE_ITEM/COMPLETE_ITEM or OPEN/REPLY/DISMISS) through the same resolver only when relevant and authorized. A task can appear in conversation, activity bubble, sticky, GUI page and 3D target with one canonical ID. User/object actions send Core commands; event replay rebuilds projections. Optional Hermes Kanban synchronization is an adapter with idempotency, provenance and conflict handling, never a new source of truth.

Kanban maps canonical lifecycle to TODO/DOING/DONE with explicit treatment for queued/waiting/failed/cancelled/retry states; board movement alone cannot invent successful completion. Planning a task for later is distinct from launching a run. Ambient mode shows workload/positions/provider markers; focused mode is readable. Physical sticky placement/movement is optional and proportional; animation failure cannot roll back a legitimate canonical transition.

Action hooks: PrepareInteraction → AcquireTarget → Navigate → Orient → BeginPhysicalAction → Contact → ExecuteSemanticAction → Verify → EndPhysicalAction → ReturnToIdle. Map these to existing action IDs and cancellation/verification semantics; do not replace the contact safety contract. Logical TYPE uses semantic text-setting when possible, authorized input fallback when necessary, and target/postcondition checks. A summoned keyboard and character-by-character visual synchronization are late polish, never authoritative input mechanisms.

### 4.12 Extensions, settings and social boundary

Provision three extension depths: **Integration** (external service connectivity), **Desktop Component** (semantic visual/physical object), and more restricted **Agent Extension** (deep reasoning/tool functions). Most extensions should use the first two. Versioned registration/configuration includes identity/source, type/version, compatibility, capability/schema references, scope/permissions, credential references and lifecycle. Core controls activation and rechecks permissions on updates; extensions cannot mutate canonical state, bypass workspace/lifecycle/staleness rules, or read unrestricted credentials. Decide execution isolation before third-party executable plugins. No plugin browser or public SDK is required now.

Configuration must serve CLI/API and future GUI: direct dialogue provider/model/endpoint/parameters; enabled reasoning harnesses/auth/model/routing priority; protected credential references; filesystem/shell/desktop/plugin/network/autonomy grants; widget/embodiment/objects/proactivity; STT/TTS/voice/barge-in; privacy scopes/social sharing/logging/storage. Use versioned validation/migration and redacted read models. Enabling a plugin is not blanket permission for all its actions.

`SocialNetworkProvider` is separate from `ReasoningProvider`, with eventual connect/disconnect/events/feed/post/reply/interact/profile operations. `NekoVerseAdapter` integrates Project N.E.K.O's social ecosystem, not its whole runtime. Prefer official API/SDK, then a permitted local sidecar/bridge, then a stable permitted direct client. The interface is unverified; undocumented endpoints are not foundational.

SORA herself participates through an allowlisted `NetworkProfileProjection` of public canonical identity, not a proxy character. `NETWORK_PUBLIC` context permits public identity/interests, explicitly social memories and network history only. Exclude private conversations/facts, files, desktop, emails, project secrets, credentials and private task contents before model invocation and outbound serialization. Public projection does not copy the private context and ask a model to redact it. Any intentional sharing uses an explicit scoped declassification path.

Inbound `SocialEvent` includes network, actor, content, timestamp and trust/provenance; deduplicate it and treat it as an external observation, never an automatic FACT. Namespace social memory by network and keep retrieval scope separate. Future autonomy levels: 0 Offline, 1 Read only, 2 React while active, 3 Occasional autonomous interaction, 4 Fully social. Outbound sends require the owner's explicit action or a valid configured grant with boundaries, rate/cost limits and revocation; merely receiving an event is not authorization. Ambient social activity uses the fast dialogue/local model rather than continuous deep reasoning. Bubbles/feed/keyboard animations are late presentation.

## 5. Phased implementation checklist

Completed boxes and original phase DoDs are preserved. New 2026-09-08 work begins unchecked and is explicitly additive. Each task has acceptance criteria; new follow-on gates do not retroactively invalidate P00–P03. Scope labels distinguish **Architecture** (required reusable foundations), **Personal** (intended personal-use features), **Public** (later extensibility), **Polish** (optional visual detail), and **Experimental** (notes only, no current implementation).

### P00 — Existing work and reproducible baseline

**Completed: 2026-09-07 18:16:17 +01:00 (Europe/London). Dependencies: none.**

- [x] **P00.1 Inventory the Hermes prototype.** Inspect location, instructions, Git/dirty state, entry points, dependencies, tests and data. **Accept:** dated reuse/gap map; if unavailable, document that fact and avoid claiming a migration assessment.
- [x] **P00.2 Establish development tooling.** Select Python version, dependency lock/dev extras, lint/type/test tools and Windows bootstrap/verify scripts. **Accept:** fresh environment reproduces existing baseline or minimal scaffold without undeclared global packages.
- [x] **P00.3 Preserve data and settle naming migration.** Back up existing state and map placeholder names to SORA. **Accept:** recoverable backup/import plan; existing identifiers are not silently broken.
- [x] **P00.4 Measure baseline.** Run available checks and record environment/results. **Accept:** current passes/failures are distinguished from historical assertions.

**Completion evidence:** `docs/verification/P00_PROTOTYPE_INVENTORY_2026-09-07.md`, `docs/verification/P00_BASELINE_2026-09-07.md`, and `changelog/2026-09-07T181617+0100_P00_GPT-5.6-Sol.md`. The legacy editable install failure is preserved as a measured baseline limitation; its six tests passed through an explicit isolated test path. No live Hermes behavior is claimed.

**DoD:** existing work is assessed or its absence recorded; reproducible bootstrap and a concrete first change scope exist. Finding old work must not overwrite user changes or these documents.

### P01 — Domain contracts and policy boundary

**Completed: 2026-09-07 18:51:57 +01:00 (Europe/London). Dependencies: P00 inventory.**

- [x] **P01.1 Version records and transitions.** Implement §4 schemas/errors/fixtures. **Accept:** round trips pass; invalid transitions/results fail; task/run/session separation is tested.
- [x] **P01.2 Specify patches, adapters and events.** Define conflicts, idempotency, cancellation, unsupported methods and ordering. **Accept:** fixtures cover duplicates, stale state, malformed output, uncertain launch and lost sessions.
- [x] **P01.3 Implement initial capability/secret rules.** Scope tool/path/action grants and approval lifecycle. **Accept:** a fake tool outside its grant is denied; injected text cannot grant authority; fixture secrets never appear in logs.
- [x] **P01.4 Publish compatibility policy.** Add ADRs and shared contract examples. **Accept:** fake Python provider and client validate the same payloads without backend-specific types leaking into Core.

**Completion evidence:** `docs/verification/P01_CONTRACTS_AND_POLICY_2026-09-07.md`, `docs/adr/0002-contract-versioning-and-compatibility.md`, schemas/examples under `contracts/`, and `changelog/2026-09-07T185157+0100_P01_GPT-5.6-Sol.md`. Hermetic verification passed 35 tests plus strict typing, lint, schema freshness, JSON parsing, and a clean wheel-install contract probe. This stage defines pure contracts/policy; durable enforcement remains P02 and live provider support remains P04–P06.

**DoD:** essential boundaries are executable and testable; malformed input and invalid authority fail closed. Avoid freezing speculative late-stage abstractions.

### P02 — Canonical state, identity, memory and context

**Completed: 2026-09-07 19:16:34 +01:00 (Europe/London). Dependencies: P01.**

- [x] **P02.1 Build repositories/migrations/outbox.** **Accept:** restart preserves history/tasks; failed transactions leave no partial state or phantom events; previous-schema fixtures migrate.
- [x] **P02.2 Load identity and manage memory.** Use all five identity files and provenance/correction/deletion/retention. **Accept:** switching providers retains identity; expired/contradictory memories remain labeled and correctable.
- [x] **P02.3 Apply validated patches.** **Accept:** a run based on revision 1942 cannot overwrite an entity changed at 1946; independent append succeeds without losing intervening conversation; replay is idempotent.
- [x] **P02.4 Compile bounded scoped context.** **Accept:** golden fixtures preserve exact constraints under truncation, exclude another project's private content and distinguish inference from fact.
- [x] **P02.5 Back up and restore.** **Accept:** clean-directory restore validates database/artifact integrity and retrieves representative identity/history; secrets are excluded or separately protected.

**Completion evidence:** `docs/verification/P02_PERSISTENCE_CONTEXT_RECOVERY_2026-09-07.md`, ADR 0003, the SORA backup/restore runbook, and `changelog/2026-09-07T191634+0100_P02_GPT-5.6-Sol.md`. Verification passed 49 tests, strict typing, lint, schema freshness, JSON fixtures, package build/install, schema-v2 initialization, and SQLite integrity. The outbox dispatcher, scheduler, leases, and interactive CLI remain P03 work.

**DoD:** state survives restart/provider replacement, conflicts are explicit, and each fact/context selection has traceable provenance.

### P03 — Concurrent text runtime and deterministic adapters

**Completed: 2026-09-07 20:14:27 +01:00 (Europe/London). Dependencies: P02.**

- [x] **P03.1 Build CLI/dialogue streaming.** Target `python -m sora`, with deliberate legacy compatibility if needed. **Accept:** inspect messages/state/tasks and use clearly labeled mock mode without credentials.
- [x] **P03.2 Implement scheduling/recovery.** Queues, leases, limits, deadlines, waits, steering/cancel and reconciliation. **Accept:** slow reasoning permits unrelated conversation; duplicate submission creates one task; restart produces no orphan leases.
- [x] **P03.3 Add fault-injecting adapters.** **Accept:** delay/failure/rate limit/bad result/disconnect/cancel race/unsupported steering/uncertain launch reach documented states without repeated effects.
- [x] **P03.4 Ground task reporting.** **Accept:** pending-work prompts never present a fabricated completed result; unavailable providers produce truthful degraded behavior.
- [x] **P03.5 Add structured observability.** **Accept:** trace a message through task/run/result/patch with correlation IDs, redacted context manifests and latency without exposing secrets.

**Completion evidence:** `docs/verification/P03_TEXT_RUNTIME_2026-09-07.md`, ADR 0004, and
`changelog/2026-09-07T201427+0100_P03_GPT-5.6-Sol.md`. Verification passed 68 tests,
strict typing, lint, schema freshness, compileall, and a clean installed-wheel vertical slice with
schema v4, SQLite integrity, one result/patch fact, six correlated traces, and zero remaining
leases. Dialogue streaming and all provider faults are deterministic mocks; no live provider or
native-session claim is made.

**DoD — G1 Text Core:** identity/history, bounded context, async reasoning, results/patches, recovery and responsive CLI work together in deterministic tests. Record real dialogue smoke coverage separately when configured.

### P03A — Additive companion and dynamic-capability foundations

**Completed: 2026-09-08 13:00:57 +01:00 (Europe/London). Dependencies: completed P01–P03.** This is an extension of existing contracts/compiler/policy/runtime, not a replacement or reopening of G1. P04 live acceptance and P05 probes can proceed independently. Subsequent desktop/client/integration work consumes these contracts.

- [x] **P03A.1 Define compatible capability and metadata extensions.** Add §4.9 descriptors/index/active-set contracts and §4.8 harness feature/configuration/display metadata. **Accept:** existing v1 fixtures and provider conformance stay valid or have an explicit versioned migration; unavailable features remain typed and aliases preserve technical provenance.
- [x] **P03A.2 Implement bounded relevance resolution.** Extend the deterministic context compiler with scoped index and lazy schema selection. **Accept:** Media and task/Kanban fixtures select only relevant details from a large synthetic registry within a declared budget; manifest explains exclusions; unrelated plugins never enter the turn.
- [x] **P03A.3 Enforce structural capability scope.** Integrate existing grants/policy at selection and dispatch, with revision-aware invalidation. **Accept:** guessed unexposed action names fail; revocation/expiry/disable/scope change between selection and execution denies action; NETWORK_PUBLIC cannot retrieve private context; REMOTE_GUEST remains unavailable.
- [x] **P03A.4 Add companion activity/control/presentation contracts.** Separate dialogue availability from per-run activity; resolve steer/cancel/new work and define result presentation. **Accept:** two mock tasks coexist with conversation; steering targets one existing run, ambiguous references require clarification, unsupported steering never claims delivery, result summaries retain authorship/evidence/limits and contain no scratchpads.
- [x] **P03A.5 Define attention/object/action projection fixtures.** Add proposed records and semantic phase hooks without Windows/Unity implementation. **Accept:** one canonical task backs multiple fixtures, expired attention cannot become an actionable target, object affordances use the resolver, and TYPE/contact/OS outcome remain distinct.
- [x] **P03A.6 Define integration/configuration/privacy contracts.** Extend existing secret/config patterns with extension classes, public profile/social-event fixtures and scoped contexts. **Accept:** redacted round trips expose no credentials, unknown extensions cannot self-grant permissions, social observations cannot become FACT automatically, and private fixture sentinels are absent from public projection and outbound payloads. No live network integration.
- [ ] **P03A.7 Connect the direct dialogue path.** Keep a configurable direct-provider interface separate from reasoning harnesses; initially validate a deterministic adapter and one supported direct provider when access is available. **Accept:** independent dialogue/reasoning selection, ongoing chat during delegation, lightweight capability dispatch through Core and separately labeled live smoke evidence; a harness configuration is not mistaken for a dialogue provider.

**Completion evidence:** `docs/verification/P03A_COMPANION_CAPABILITY_FOUNDATIONS_2026-09-08.md`, and `changelog/2026-09-08T130057+0100_P03A_Gemini-3.8-Flash.md`. Verification passed 106 tests, strict typing across 74 source files, lint, schema freshness check for 10 new contracts, and test suites across capabilities, attention, desktop objects, social boundary, and companion UX.

**DoD — G1A Companion Architecture:** P03A.1–P03A.6 additive contracts, resolver, security checks and deterministic scenarios pass without changing prior completion records. P03A.7 live dialogue acceptance is a separate follow-on requirement for a usable conversational client; unavailable credentials do not block contract work or P04/P05. No widget, plugin marketplace, social network or peer transport is built by this gate.

### P04 — First live reasoning adapter: Hermes

**Completed: 2026-09-08 08:29:02 +01:00 (Europe/London). Required for original backend roadmap. Dependencies: G1.**

- [x] **P04.1 Verify the intended Hermes product/version.** Probe supported API/CLI, auth, sessions, events, permissions, cancellation and terms using official sources. **Accept:** evidence-backed capability matrix; no invented protocol/private endpoint dependency. **Evidence:** official ACP documentation/source inspection plus local `hermes --version`, `hermes status`, `hermes acp --version`, and `hermes acp --check`; exact build and matrix are in `docs/verification/P04_HERMES_LIVE_2026-09-08.md`.
- [x] **P04.2 Implement normalized adapter.** **Accept:** conformance suite passes for sessions, results, failures and cleanup without Hermes branches throughout Core. **Evidence:** credential-free fake ACP subprocess tests, strict static checks, 78-test repository suite, and fresh-wheel capability/CLI probes pass.
- [x] **P04.3 Run bounded live scenarios.** **Accept:** start/resume where supported, concurrent dialogue, cancellation/error and patch proposal evidence with exact version and redacted artifacts. **Evidence:** the original isolated tool-free matrix on Hermes Agent 0.21.0 passed start, responsive concurrent dialogue, native-session resume, cancellation, normalized result, and Core-mediated patch persistence. Workspace remained empty, SQLite quick-check passed, and no runtime lease remained. A later trust-policy amendment enables Hermes-native tools by default; subsequent tool probes timed out and are not misreported as successes.

**Completion evidence:** `docs/verification/P04_HERMES_LIVE_2026-09-08.md`, `docs/adr/0005-hermes-acp-provider-boundary.md`, `changelog/2026-09-08T082902+0100_P04_GPT-5.6-Sol.md`, and the later `P04-AMENDMENT_GPT-5.6-Sol` changelog. The original GPT-5.6 Luna implementation record is retained separately. Hermes is trusted to manage its native tools; SORA still reports `tool_restrictions=false` and does not describe the assigned cwd as an OS sandbox.

**DoD:** real Hermes returns validated results without blocking dialogue or bypassing Core. If supported integration is unavailable, retain an unavailable adapter and a precise blocker; do not mark live integration complete.

### P05 — Codex and safe single-writer coding

**Required. Dependencies: G1 and P01 grants. Reuse P04 patterns, but a Hermes blocker need not block this phase.**

- [x] **P05.1 Probe supported Codex interface.** **Accept:** actual auth/thread/event/cancellation/tool restriction/model-discovery capabilities documented with a minimal supported probe. **Evidence:** Codex CLI 0.153.4 App Server initialization/model schema probed; active ChatGPT auth confirmed without copying credentials; six visible models discovered; start/resume/events/steer/interrupt/approval/sandbox matrix recorded in `docs/verification/P05_CODEX_APP_SERVER_2026-09-08.md`.
- [x] **P05.2 Implement adapter/project-thread mapping.** **Accept:** conformance tests and a live read-only repository task preserve scope and native session identity. **Evidence:** `CodexAppServerProvider` plus fake-server lifecycle coverage; GPT-5.6 Luna low-effort live fixture stayed read-only, resumed the same native thread, and live interruption reconciled as cancelled. A Core vertical run atomically persisted the native Codex thread in the agent-session record and run payload with a `session.attached` trace.
- [x] **P05.3 Add initial workspace isolation before writes.** Allocate owned worktree from explicit base, record ref/path/dirty state and write lease. **Accept:** task changes stay isolated; source checkout and user changes remain intact. **Evidence:** durable owned-worktree records and exclusive leases implemented; unit acceptance preserved a dirty source checkout; live Luna changed only an isolated committed fixture and produced attributable base/head/status/diff evidence. Direct CLI remains read-only and unowned write modes fail closed.
- [ ] **P05.4 Produce reviewable coding artifacts.** **Accept:** bounded SORA change returns diff/base/head, commands/tests, uncertainties and evidence; no automatic merge or unverified completion claim.

**Progress evidence:** ADR 0007, `docs/verification/P05_CODEX_APP_SERVER_2026-09-08.md`, and `changelog/2026-09-08T143852+0100_P05-PROGRESS_GPT-5.6-Sol.md`. P05.4 remains open because this SORA checkout has no commit/`HEAD`; no truthful full-project worktree can be allocated until a base exists. No SORA files were staged or committed. The progress log also records that this work was verified against Gemini 3.8 Flash's completed P03A and P06 implementation in the combined live tree.

**DoD:** real Codex can inspect/change an isolated SORA workspace, report activity and truthful cancellation, and return attributable results. Backend sessions remain working context.

### P06 — Antigravity and rule-based routing

**Implemented: 2026-09-08 13:55:00 +01:00 (Europe/London). Required capabilities; live availability may block an adapter. Dependencies: G1; complete P05 per-task allocation/full-SORA acceptance before routed coding writes. NOTE: P05 must be finished before P06 is complete.**

- [x] **P06.1 Verify/implement Antigravity adapter.** **Accept:** supported interface, sessions/projects/events/recovery matrix, conformance tests and live evidence; unavailable integration is reported honestly. **Evidence:** non-interactive `agy.exe` (`--output-format json`, `--effort`, `--print="..."`) wrapped in `AntigravityProvider`, capturing native conversation ID, supporting session resumption (`--conversation <id> --continue`), timeout, process cleanup, and result normalization. Conformance verified with 11 tests in `tests/providers/test_antigravity.py`.
- [x] **P06.2 Implement deterministic routing.** `auto`, manual override, dialogue/lookup fast paths, coding/research/alternative rules. **Accept:** fixtures respect capability, privacy, budget and grants, with persisted rationale. **Evidence:** `RoutingEngine` with fast-paths, intent classification, and privacy scope filtering. Conformance verified with 11 tests in `tests/routing/test_routing.py`. Although P05.3's initial owned-worktree manager now exists, routed coding writes retain `p05_deferred=True` until per-task allocation and P05.4 close the overall P05 gate.
- [x] **P06.3 Bound retries/fallback.** **Accept:** no retry storms or cloud fallback for local-only context; explicit backend requests are not silently substituted; auto fallback records the actual provider. **Evidence:** explicit backend selections fail-fast with `ProviderLaunchError(UNAVAILABLE)` and empty fallback; auto routing records `routing.fallback` event traces and updates run provider.
- [x] **P06.4 Integrate companion delegation and steering.** **Architecture/Personal; depends on P03A.4 and negotiated adapter capabilities. Accept:** natural coding/research requests create scoped tasks without a task-creation form; Cody/Hermes/AG can work concurrently when resources permit; ordinary conversation stays available; “tell him not to change the public API” reaches the correct existing task only when supported and acknowledged. Unknown/ambiguous references do not affect arbitrary work. **Evidence:** `disambiguate_steering` resolves natural references ("Cody", "Hermes", "Antigravity"/"AG", or pronouns) when unambiguous, rejecting ambiguous references. `runtime.steer_from_conversation` steers targeted runs.
- [x] **P06.5 Present attributable outcomes adaptively.** **Personal; depends on P03A.4. Accept:** small fix, significant change, research artifact, failure and decision-needed fixtures select SILENT/BRIEF/EXPLAIN/WALKTHROUGH appropriately, retain evidence qualifiers and expose full traces on demand. Physical presentation is optional and uses P10/P11 when available. **Evidence:** `runtime.present_result` evaluates significance, findings, diffs, and failures to choose presentation modes with specialist identities.

**Completion evidence:** `docs/verification/P06_ANTIGRAVITY_ROUTING_2026-09-08.md`, `docs/adr/0006-antigravity-adapter-and-rule-based-routing.md`, and `changelog/2026-09-08T135500+0100_P06_Gemini-3.8-Flash.md`. Verification passed 135 tests, strict mypy across 80 source files, and clean lint.

**P05 Dependency & Deferred Scope Notice:** P05 must be finished before P06 is complete. P05.1–P05.3 now provide live Codex read-only evidence and the initial owned-worktree/lease boundary, but the current SORA checkout has no base commit for P05.4. Routed coding writes therefore remain held with `p05_deferred=True` until per-task allocation and full-SORA acceptance are wired and verified. P06 does not retroactively claim Codex acceptance as its own evidence.

**DoD:** routing is predictable and inspectable. Do not claim all three backend integrations until each has separate live acceptance evidence.

### P07 — Parallel workspaces, synthesis and review

**Required for concurrent coding; parallel use remains selective. Dependencies: P05.3, routing, two usable adapters or doubles for contract tests.**

- [ ] **P07.1 Complete workspace manager.** Create/track/diff/recover/discard/cleanup. **Accept:** writers cannot share a lease; resolved-path protection and dirty-artifact recovery prevent unrelated deletion.
- [ ] **P07.2 Add bounded independent fan-out/synthesis.** **Accept:** budgets and provenance remain separate; disagreement/failure stays visible; synthesis cannot invent agreement or execute result instructions.
- [ ] **P07.3 Add review/integration workflow.** **Accept:** selected diff integration preserves other work, exposes conflicts, runs appropriate validation and follows current merge authorization; rollback is documented.

**DoD — G2 Agent Workbench:** proven adapters, routing, isolated writes and optional independent review operate together. Mock-only and unavailable capabilities remain explicit.

### P08 — Authenticated API and reconnectable clients

**Required before client control. Dependencies: G1 and P01; may proceed alongside adapters.**

- [ ] **P08.1 Implement versioned HTTP/WS over Core services.** **Accept:** CLI/API behavior matches; scope, pagination, limits, idempotency and errors are tested.
- [ ] **P08.2 Implement snapshot/event replay.** **Accept:** reconnect between commit/delivery loses no durable update; duplicates deduplicate; expired cursor resnapshots; slow client does not block Core.
- [ ] **P08.3 Secure local boundary.** Loopback by default, local authentication, protected secrets, host/origin/WS validation. **Accept:** unauthorized/untrusted-origin/cross-device operations fail; no tokens in URL logs.
- [ ] **P08.4 Add lifecycle supervision.** **Accept:** clients can close independently; graceful restart reconciles tasks and reconnects without duplicate launch; health/readiness distinguish degraded providers.

- [ ] **P08.5 Expose generic companion/configuration projections.** **Architecture; depends on G1A. Accept:** authenticated APIs expose independent dialogue/task activity, artifact/referent IDs, capability availability, validated redacted settings and object projections; widget, expanded GUI and Unity fixture consumers converge after reconnect. No polished GUI required.
- [ ] **P08.6 Register selected integrations and object affordances.** **Architecture; depends on P03A.6 and P08 authorization. Accept:** a built-in fake Integration/Desktop Component enables/disables cleanly, versioned schemas load lazily, disable/revoke invalidates active sets, and no extension writes canonical repositories directly. Keep third-party executable loading and marketplace work deferred.

**DoD — G3 Client Boundary:** two authenticated clients share consistent state and recover events; boundary tests pass. Private networking is not yet authorization to expose development endpoints.

**Additive G3 acceptance:** P08.5–P08.6 are required before shipping extension-backed objects or configurable companion clients. Existing HTTP/WS/auth/recovery criteria remain unchanged.

### P09 — Unity overlay and coordinate foundation

**Required. Dependencies: G3; isolated rendering spikes may use fixtures earlier.**

- [ ] **P09.1 Validate Unity/VRM/overlay combination.** **Accept:** packaged Windows build imports a licensed VRM, renders transparent/always-on-top, accepts avatar clicks and passes other input through.
- [ ] **P09.2 Implement client and deterministic movement.** Idle, left/right movement, look-at, reconnect and safe hydration. **Accept:** Unity exit does not stop Core and no inference occurs in the simulation loop.
- [ ] **P09.3 Define coordinate transforms.** Physical pixels in Windows virtual desktop; explicit origin/units/y direction, monitor/topology, world depth/reach plane and inverse mapping. **Accept:** fixtures cover offsets, negative coordinates, portrait displays, mixed DPI, taskbar positions and monitor gaps without double scaling.
- [ ] **P09.4 Handle topology changes.** **Accept:** resolution/DPI/hotplug/sleep-resume updates relocate an offscreen avatar safely; distinguish actual hardware coverage from synthetic layouts.
- [ ] **P09.5 Add visual debugging/performance baseline.** **Accept:** target rectangles and screen/world/nav/IK points are inspectable; mathematical round trips are within one physical pixel; separately record visual alignment and packaged frame time.

- [ ] **P09.6 Provide a separate SORA marker and semantic hooks.** **Architecture/Personal; depends on P03A.5 and P09 coordinates. Accept:** overlay can mark/highlight a scoped target without moving the Windows pointer, expose interpreted target for spatial clarification, and consume semantic action phases independently of animation assets.

**DoD:** SORA moves/looks at validated positions without stealing unrelated input. Target stable 60 FPS initially; 120 Hz is optional measured tuning.

### P10 — UI Automation perception and pointing

**Required. Dependencies: P09 coordinates and desktop policy.**

- [ ] **P10.1 Build bounded Windows bridge.** Enumerate windows, focus, UI trees, semantic targets/rectangles. **Accept:** known fixture controls resolve; hung/inaccessible/elevated applications yield typed errors without freezing Core or escalating privileges.
- [ ] **P10.2 Implement target lifecycle and levels 0–2.** **Accept:** observation/presentation/navigation grants are distinct; stale/closed/ambiguous targets cannot silently become actionable; revocation is respected.
- [ ] **P10.3 Implement walk/turn/point.** **Accept:** moved/disappeared target retargets or fails gracefully without executing any UI action.
- [ ] **P10.4 Build contextual editor handoff.** Use reliable UIA or app integration for repository/file/selection. **Accept:** exact fixture selection reaches the task and verified findings can be pointed at; missing editor metadata is reported, not guessed.

- [ ] **P10.5 Add volatile cursor/selection tracking and gestures.** **Personal; depends on P03A.5, P10.1 and coordinate contracts. Accept:** bounded ring buffer is absent from canonical storage/logs, fixture hover/click/selection/circle trajectories resolve correctly, geometric false positives are rejected and buffer expiry is explicit. Later jab/wiggle/underline remain optional.
- [ ] **P10.6 Implement attention/reference resolution.** **Architecture/Personal; depends on P10.5 and P09.6. Accept:** UI/project/file/task/document/object candidates support “this/that/it”; the same unexpired target serves “Look at this” then “Can Cody fix it”; moved/pinned/expired/ambiguous targets revalidate or show a spatial clarification marker. No low-confidence target silently authorizes action.
- [ ] **P10.7 Open real content through configured handlers.** **Personal; depends on P08.5 settings, P10.6 and navigation grants. Accept:** “Show me/Open it/Where?” opens/focuses a fixture repository, file or artifact in its configured handler and highlights/points when supported; invalid paths/arguments and ambiguous referents fail safely; unsupported navigation is reported precisely.

**DoD:** semantic pointing and verified coding context handoff work. Do not assume UIA exposes every editor's file/selection.

**Additive spatial gate:** P10.5–P10.7 demonstrate selection/circle → attention → follow-up delegation and conversational result → real content display. P14.5 later adds spoken-time alignment; current text/fixture acceptance does not claim live STT integration.

### P11 — Procedural reaching and physical button action

**Required major demo. Dependencies: P10, rigging and action coordinator.**

- [ ] **P11.1 Add animation/IK layering.** Hand/fingertip, gaze/aim, arm choice, reachable-space checks, blending/retraction; allow later foot targets. **Accept:** inside/outside reach and left/right/interrupted fixtures end in valid controller state.
- [ ] **P11.2 Add deterministic interaction state machine.** Navigate → align → reach → contact → verify → retract. **Accept:** grab, disconnect, cancellation, timeout and target loss abort pending effects safely; controllers arbitrate animation/IK ownership.
- [ ] **P11.3 Implement authorized Level 3 action.** **Accept:** target/grant rechecked at contact; repeated contact/expired grant/moved control/crash-window tests cause no blind repeat effect; unknown outcome remains explicit.
- [ ] **P11.4 Demonstrate Pause.** Start with a deterministic media fixture, then Spotify if its actual UI/API supports a reliable target. **Accept:** recorded walk/turn/reach/contact/invoke/postcondition/retract; playback changes, not merely animation completion.

- [ ] **P11.5 Add logical typing and presentation hooks.** **Personal architecture; depends on P03A.5, P10.6 and Level 3 checks. Accept:** permitted fixture text insertion uses semantic text-setting or explicitly authorized input fallback, rechecks target, and verifies content independently of animation; interrupted insertion reports partial/unknown outcome. Detailed keyboard animation remains P15.12 polish.

**DoD — G4 Embodied Action:** a scoped semantic action synchronizes with physical contact and verifies its outcome. General autonomous Level 4 control remains deferred.

### P12 — Grabbing, physics, recovery and window surfaces

**Required for full embodiment. Dependencies: P09 controller and P11 arbitration.**

- [ ] **P12.1 Grab/drag/release.** Raycast collider/body anchor, spring/damping and bounded release inertia. **Accept:** cross-monitor/DPI dragging and capture loss release safely while desktop click-through works.
- [ ] **P12.2 Secondary motion/simple falling.** Tune SpringBone and simplified support-loss physics first. **Accept:** repeated drag/drop settles without explosive forces or invalid numeric state.
- [ ] **P12.3 Ragdoll and recovery.** Joints/limits/collisions, orientation/settle detection, blended get-up and safe timeout reset. **Accept:** front/back/side scenarios recover without animation/IK/ragdoll fighting over bones.
- [ ] **P12.4 Window surfaces.** Monitor bottom, taskbar and selected window tops; moving/minimized/closed/occluded supports. **Accept:** support changes behave predictably with bounded colliders, not geometry for every UI element.
- [ ] **P12.5 Semantic feedback.** Grab/release/fell/landed/support-removed/click/poke/completed/failed with debounce/cooldowns. **Accept:** Core receives meaningful events without per-frame inference or reaction storms.

- [ ] **P12.6 Connect generic desktop-object affordances to physical verbs.** **Architecture/Personal; depends on P03A.5 and P08.6. Accept:** a fixture object can be looked at/pointed at/touched under its policy; hidden/private objects expose neither contents nor affordances; presentation failure leaves canonical state intact. Implement one reusable bridge, not every proposed object.

**DoD:** repeated grab/fall/recover and support-removal scenarios remain stable; debugger exposes controller, physics and target state.

### P13 — Desktop awareness and on-demand vision

**Required awareness. Dependencies: P10, capture policy/retention; independent of advanced physics.**

- [ ] **P13.1 Subscribe to desktop events.** Foreground/window/dialog/task changes, dedupe, debounce and attention policy. **Accept:** event bursts invalidate stale context without inference/speech storms.
- [ ] **P13.2 Add scoped capture fallback.** Evaluate Windows.Graphics.Capture or supported equivalent. **Accept:** only needed region/window is captured, revocation stops capture, retention is bounded and there is no continuous VLM loop.
- [ ] **P13.3 Normalize vision evidence.** Timestamp, region/frame mapping, provenance, confidence, expiry. **Accept:** low-confidence/stale detections cannot authorize a click or become permanent facts automatically; captured instructions cannot grant authority.

- [ ] **P13.4 Join attention targets with cropped fallback.** **Personal; depends on P10.6 and P13.3. Accept:** a circled UIA-insufficient region produces only a scoped crop with timestamp/frame/provenance; the resulting target can be reused for a task without persisting raw cursor streams or exposing unrelated desktop regions.

**DoD:** UIA-insufficient fixtures can be interpreted on demand with auditable scope/cost. Semantic perception remains the default.

### P14 — Voice and lip sync

**Required voice experience. Dependencies: G1/G3; P09 for visual lip sync, not advanced physics.**

- [ ] **P14.1 Benchmark VAD/STT/TTS.** **Accept:** record hardware, model files/licenses, quality, memory and cold/warm latency; choose measured defaults without requiring LiveKit early.
- [ ] **P14.2 Stream voice sessions.** Mic/VAD/STT → Core → dialogue → TTS/playback; echo/device-loss handling. **Accept:** finalized speech creates one durable message and partial transcripts never duplicate turns.
- [ ] **P14.3 Implement barge-in.** **Accept:** cancellation stops generation/queued audio/lip sync; stopping speech does not cancel underlying reasoning unless requested.
- [ ] **P14.4 Synchronize mouth/emotion.** Audio clocks/visemes or validated amplitude fallback. **Accept:** pause/disconnect/interrupt resets mouth; stale audio cannot animate later turns; no model frame commands.

- [ ] **P14.5 Align speech references and interruption intent.** **Personal; depends on P10.5–P10.6 and P03A.4. Accept:** delayed-transcription tests resolve the cursor at the spoken phrase's timestamp rather than at STT completion; missing timing/buffer history yields clarification. Live tests distinguish stopping TTS, steering a named task, cancelling it and starting unrelated work.

**DoD — G5 Voice:** spoken conversation, interruption, privacy controls and truthful task reporting work. Provisional warm p95 targets: playback stops within 250 ms of detected interruption, first audio within 2 s after end-of-utterance on reference hardware. Measure and revise through a recorded decision rather than claim untested performance.

### P15 — PWA, private access, packaging and advanced behavior

**Required clients/release, then polish. Dependencies: G3; P14 for voice UI; security gate before remote use.**

- [ ] **P15.1 Build responsive installable PWA.** Conversation, mic, tasks/agents, optional traces, steer/cancel. **Accept:** clients converge after reconnect; service workers do not silently cache sensitive API responses.
- [ ] **P15.2 Add private remote transport.** Pair/revoke devices, scoped sessions, encrypted browser-compatible transport, rate limits/audit. **Accept:** paired phone connects, revoked/unpaired devices fail, private-network membership alone grants no control; no public dev endpoint.
- [ ] **P15.3 Package and document operations.** Core/bridge/Unity builds, install/update/uninstall, optional startup, assets/models, backup/restore/rollback. **Accept:** clean Windows profile install and state-preserving upgrade pass; personal data handling is explicit.
- [ ] **P15.4 Run integrated user scenarios.** Conversation, telemetry-file analysis, isolated coding, exact editor context, multi-monitor pointing/press, physics, voice and mobile reconnect. **Accept:** each scenario links evidence/environment/limits.
- [ ] **P15.5 Add advanced behaviors after foundations.** Running/waving/sitting/leaning/climbing, nuanced gaze, physical attention, configurable proactivity/quiet modes. **Accept:** distraction can be limited and behavior respects grants/controller arbitration.

- [ ] **P15.6 Build compact widget and expanded chat.** **Personal; depends on P08.5, direct dialogue acceptance and P06 presentation. Accept:** persistent configurable anchor (initial candidate bottom-right), input, attachments/references, activity bubble, specialist indicators, lightweight notifications and expansion into readable code/files/images/docs/history; SORA remains available during multiple delegated runs; technical detail is collapsible and private reasoning absent. Test keyboard access, mixed DPI, clutter/quiet controls and reconnect.
- [ ] **P15.7 Build full application/settings surfaces.** **Personal; depends on P08.5 and P15.6 shared models. Accept:** Chat/Activity/Content/Integrations/Settings expose §4.12 configuration, credentials remain protected/redacted, permissions/context scopes are inspectable, artifacts open in configured apps, and steer/cancel are explicit. Runtime state is identical across widget, full app, PWA and avatar. Technology/visual design remains deferred until this stage.
- [ ] **P15.8 Build canonical Kanban desktop object.** **Personal; depends on P08.6, P12.6 and canonical task projection. Accept:** “fix this later” creates one planned task with no automatic run; “get Cody to do it” starts a run under that task; TODO/DOING/DONE and waiting/failure/cancel/retry mappings stay consistent across board/chat/GUI. Ambient/focused modes are legible; animations are proportional and optional. Hermes board sync is optional and never canonical.
- [ ] **P15.9 Add NekoVerse social adapter.** **Optional personal integration; depends on P03A.6/P08.6 and a verified supported external interface. Accept:** independently conformed SocialNetworkProvider, public identity projection of SORA herself, deduplicated untrusted social events, separate social memory and NETWORK_PUBLIC leak tests pass; offline/read-only defaults and bounded granted sends work. Verify official API/SDK or permitted bridge/direct-client strategy before live use; no private endpoint assumption.
- [ ] **P15.10 Add extension management UI.** **Public; depends on P08.6, P15.7 and chosen execution/isolation/update model. Accept:** installed integrations/components can be inspected, enabled/disabled/configured/updated/removed with capability/privacy/credential review; update cannot silently gain permissions. Browser/catalog and third-party distribution remain a separately accepted public-product scope.
- [ ] **P15.11 Document public harness adapter mechanism.** **Public; depends on sufficiently exercised Hermes/Codex/AG contracts and P03A.1 metadata. Accept:** an independent fixture adapter maps TaskRequest/AgentEvent/AgentResult, advertises unsupported features honestly and passes lifecycle/permission/staleness/workspace tests without changing Core. DeepSeek Harness, OpenClaw and custom/local harnesses are examples, not current compatibility promises or required implementations.
- [ ] **P15.12 Add proportional object/social/typing animation polish.** **Polish; depends on relevant P11/P12/P15.8–P15.9 semantics. Accept:** optional sticky placement, summon-keyboard and social bubbles convey significance, honor quiet/clutter limits, and can be disabled without changing task/input/social outcomes. Social autonomy levels beyond read-only require explicit configured grants, rate/cost bounds and revocation; no continuous frontier reasoning.

**DoD — G6 Integrated Release:** documented installation supports the selected proven providers, persistent state, embodied interaction, voice and authenticated PWA/private access. Unsupported features remain explicit; full specification completion requires all required individual gates.

**Additive companion release acceptance:** P15.6–P15.8 complete the intended personal desktop surfaces; P03A/P06/P10/P14 follow-on acceptance supplies responsive dialogue, contextual presentation and reference handling. NekoVerse is optional and availability-dependent; public extension management/SDK and polish do not block the personal release. Peer visits are excluded entirely. No early full-GUI or plugin-browser phase is added.

## 6. Dependency sequencing and first work batch

```text
P00 → P01 → P02 → P03 [G1]
                    ├→ P04 Hermes
                    ├→ P05 Codex + initial workspace safety
                    ├→ P06 Antigravity/routing → P07 [G2; also needs P05]
                    └→ P08 [G3]
                         ├→ P09 → P10 → P11 [G4] → P12
                         │          └→ P13 events/vision
                         ├→ P14 [G5; lip sync also needs P09]
                         └→ P15 clients/private transport
                              + selected G2/G4/G5/P12/P13 → G6
```

Do not gate API work on every vendor, voice on ragdoll polish, or initial coding safety on the later parallel-workspace milestone. P04/P06 unavailable integrations can remain blocked while independent work proceeds; they cannot be represented as completed.

The original first implementation batch, P00 → P01 → P02 → P03, and P04 are complete under their recorded acceptance. P04 was amended so trusted Hermes-native tools and configured integrations remain enabled by default; a successful live native-tool scenario is not yet claimed. P03A.1–P03A.6 and P06 implementation are recorded separately. Continue P05 from its explicit full-SORA Git-base boundary. Live dialogue P03A.7 is distinct from reasoning-provider probes. Calendar estimates should use actual throughput, not reset the historical baseline.

Additive dependency map:

```text
Completed P01/P02/P03 → P03A.1–.6 [G1A]
                          ├→ P03A.7 direct dialogue → usable companion client
                          ├→ P06.4/.5 conversational control/presentation
                          ├→ P08.5/.6 client/settings/extension projections
                          └→ P03A.5 attention/object contracts
P09 coordinates/marker + P10 UIA → P10.5/.6 references → P10.7 real-content display
P10.5/.6 + P14 speech timing → P14.5 spoken-reference acceptance
P08.6 + P12.6 → P15.8 Kanban; P08.5 + direct dialogue → P15.6/.7 widget/full app
Public-scope fixtures + P08.6 + verified social interface → optional P15.9
Exercised adapters → public P15.11 SDK (late)
Peer/guest concepts → notes only; no active dependency or delivery gate
```

Provider metadata, semantic action hooks, attention/object fixtures and versioned configuration are near-term architectural provision. Rendering, polished widget/full GUI, social presentation, plugin browser and public SDK remain late. Actor/scope fields support today's boundaries without creating a guest protocol or transport now.

## 7. Verification and observability

| Layer | Required evidence |
|---|---|
| Core unit/property | Transition matrix, conflicts/duplicates, context bounds, provenance, scope, routing |
| Core integration | Concurrent dialogue/runs, migrations/restart, leases, approval expiry, cancellation races, backup/restore |
| Adapter conformance | Unsupported methods, bad output, timeouts/rate limits, lost sessions; same fixtures across adapters, separate live reports |
| Security | HTTP/WS auth/origin/host failures, revoked grants, path escapes, injected UI/file/backend text, secret redaction |
| Windows | Known UIA fixture, hung/inaccessible process, stale/moved targets, semantic action and postcondition |
| Coordinates | Forward/inverse mapping, mixed DPI, negative/portrait/gapped layouts, topology invalidation, hardware calibration |
| Unity | Move/look/point/reach, contact races, drag/drop/recover, support loss, reconnect; PlayMode/EditMode plus packaged runs |
| Voice/clients | Transcript dedupe, echo/barge-in, device loss, lip sync reset, mobile revoke/reconnect, measured latency |
| Release | Clean install, upgrade/migration/rollback, restore, independent Core/bridge/Unity restart |
| Dynamic capabilities | Large synthetic registry under fixed budget; lazy relevant schema loading; forbidden IDs absent and guessed calls denied; revoke/disable/expiry/cache-scope races |
| Companion UX | Dialogue plus simultaneous independent tasks; acknowledged steering versus queueing; truthful aliases/authorship; no global THINKING or scratchpad display; proportional result modes |
| References/objects | Delayed STT with moved pointer; expired/pinned targets; false circles; spatial clarification; show/open handler checks; one canonical task across all projections; animation failure independence |
| Extensions/social | Config round trips and version migration; disabled extension dispatch denied; public-context/outbound sentinel leak tests; untrusted social memory; scoped consent/revocation and rate limits |

Required end-to-end additions: selected-code “look at this” → Cody delegation → unrelated chat → acknowledged steering → attributable result/show; circle → attention target → scoped vision crop only if needed → follow-up task; “put this on the board” → only Tasks/Kanban schemas → one planned task → later run → consistent board; optional social event → NETWORK_PUBLIC → permitted response with no private sentinels. Peer examples are design-review scenarios only, not current integration tests.

Default tests are hermetic. Live providers, desktops, microphones and GPUs are opt-in suites; skipped tests are not passes. Use meaningful behavioral tests appropriate to each change. Record exact commands and environment in `docs/verification/` when those files are created.

Provisional operating budgets:

- No external wait holds a database write transaction or blocks Core's event loop.
- Target local state/task-query p95 ≤100 ms under a documented modest concurrent workload; measure provider inference separately.
- Configure worker/queue/output/artifact limits, per-run tokens/spend/deadlines, retry bounds and client backpressure. Ratify defaults against P03 hardware/workload.
- Target stable 60 FPS; set frame-time, idle CPU/GPU and memory limits from P09 measurements. Keep physics/collider counts bounded.
- Bound visual capture frequency/size and debounce semantic reactions; idle animation should consume no reasoning quota.
- Label usage measured, provider-reported, estimated or unavailable.

Developer inspection: task/run/backend/model, canonical revision, queue/lease, context sources, grants/approvals, window/target, screen/world coordinates, behavior/IK/physics and failures. Normal UI keeps traces optional. Log IDs/metadata by default; raw personal-content diagnostics require scoped capture and retention.

## 8. Risks and open decisions

| Risk | Mitigation / checkpoint |
|---|---|
| Existing prototype absent or incompatible | P00 inventory and backup before rewrite/migration |
| Unsupported backend automation | P04–P06 official capability probes; unavailable adapters and mocks; no invented private protocol |
| Stale/duplicate results corrupt state | Entity preconditions, idempotency, transactional outbox, cancellation reconciliation |
| Crash after an external action | Persist attempt, verify/reconcile postcondition, preserve unknown outcome; no blind retry |
| Prompt injection/memory poisoning | Treat retrieved/UI/backend content as data; grants and patch checks outside models |
| Worktree confused with sandbox | Actual provider/tool/path restrictions; do not imply host isolation without evidence |
| UIA incomplete or hung | Bounded bridge process, app integration and on-demand vision; unknown metadata stays unknown |
| Overlay/input failures | Early packaged hardware spike; avatar hit-testing, click-through, safe hide/exit |
| DPI/topology misalignment | Explicit coordinate frames, calibration, topology invalidation, semantic recheck at contact |
| IK/animation/ragdoll instability | Deterministic bone ownership, bounded forces, simple falling before ragdoll, recovery timeout |
| Personal-data leakage | Scope capture/context, redact logs, protect secrets, inspect/delete memory and retention artifacts |
| Remote control exposure | G3 tests, app auth and device revocation before private remote access |
| Licensing/hardware surprises | Pin dependencies and record terms/footprint as each subsystem is selected |
| Scope overwhelms usable core | Gate-based slices; defer autonomous control, native mobile and polish |
| Context explosion from installed plugins/object affordances | Small scope-filtered capability index, bounded lazy details, large-registry budget fixtures in P03A |
| Capability overreach or stale authorization cache | Permission-aware resolver plus authoritative dispatch; guessed-ID rejection, revision-keyed cache and immediate revocation checks |
| Provider coupling or misleading friendly identities | Extend negotiated metadata; retain technical provenance and explicit unsupported features; keep direct dialogue separate from harnesses |
| Plugin creep into a generic agent platform | Selected semantic capabilities and three extension depths; specialist harnesses retain complex tool work |
| Desktop ambiguity from pointer/STT latency | Volatile timestamped history, attention expiry, geometric confidence, spatial clarification and semantic revalidation |
| UI clutter and task-console experience | Compact/expanded surfaces, ambient/focused board, quiet settings and proportional movement; dialogue remains primary |
| NekoVerse/social privacy leakage | Allowlisted public projection before context compilation/serialization; separate social namespace; explicit sharing/grants and outbound leak fixtures |
| Duplicate state across Kanban/widget/GUI | Canonical IDs/events and replayable projections; board/animation never owns task transitions |
| Future remote-agent overreach | Experimental concern only: local mediation, deny-by-default leases, redacted scene graph and target-risk enforcement; no transport implementation now |

Record ADRs with date, evidence, alternatives, consequences and migration/reversal plan. Defaults below are provisional:

| ID | Decision | Working default / decide by |
|---|---|---|
| D01 | Prototype location/naming | SORA everywhere new; migrate legacy identifiers after P00 inventory |
| D02 | Python/storage/deployment | Async Python/SQLite, Windows user process; validate tooling and concurrency in P00–P02 |
| D03 | Exact Hermes product/backend surfaces | Supported interfaces only; determine in each adapter probe |
| D04 | Dialogue model/fallback | Deterministic mock verified in P03; direct model IDs/access belong to P03A.7, separate from P04–P06 harness probes; local fallback later |
| D05 | Memory writing/retention | Provenance, policy-validated proposals, minimal transient retention; P02 |
| D06 | Windows helper transport | Provisional C# process with authenticated local IPC; deployment/timeout spike by P09–P10 |
| D07 | Unity/VRM/overlay strategy | Pin validated versions; compare one virtual-desktop versus per-monitor windows in P09 |
| D08 | World depth/reach plane | Explicit deterministic desktop-plane projection; P09/P11 fixtures |
| D09 | Voice/GPU allocation | Benchmark source candidates on actual hardware in P14 |
| D10 | Remote/realtime transport | Private network + app auth; LiveKit only if needed, P15 |
| D11 | Proactivity | Reactive default, quiet mode, remembered scoped grants; before P13/P15 reactions |
| D12 | Schedule/release scope | No unsupported dates; estimate after P00 and first vertical-slice throughput |
| D13 | Capability index/selection budget and caching | Deterministic relevance first, bounded schemas and scope/version-keyed caches; ratify with P03A large-registry fixtures |
| D14 | Desktop client toolkit/window strategy | Shared Core models for widget/expanded/full app; choose after API and Windows input/DPI spike, polish in P15 |
| D15 | Gesture thresholds/buffer duration/clock alignment | Bounded volatile capture, natural hover/circle/click/selection; measure false positives and STT delay in P10/P14 |
| D16 | Object layout/affordances and Kanban mapping | Canonical projections, ambient/focused views, private default; settle exact status mapping in P15.8 |
| D17 | Extension execution/update/trust model | Built-in constrained registration first; isolation/signing/distribution decisions before third-party executable loading, P15.10 |
| D18 | NekoVerse public interface and social policy | No verified integration claimed; official SDK/API or permitted bridge; read-only/offline default and explicit scope/grants, P15.9 |
| D19 | Public harness SDK compatibility | After Hermes/Codex/AG exercise abstraction; capability negotiation and conformance rather than hardcoded vendor list, P15.11 |
| D20 | Guest/peer protocol and capability leases | Experimental only; preserve §12 assumptions, no implementation schedule or active dependencies |

Initial planning decisions: preserve original source; distinguish actual implementation evidence from source assertions; use SORA as the actual name; introduce initial coding isolation before any write adapter; authenticate Core before remote control. These are planned controls, not implemented guarantees.

2026-09-08 decisions: companion-first surfaces; direct dialogue versus specialist harnesses; dynamic permission-aware capability loading as real additive architecture; temporary spatial referents; canonical desktop-object projections; separate social provider/public context; generic extension/configuration boundaries. Detailed client design, plugin browser, animation catalog, public SDK and social autonomy remain deferred. Guest visits are experimental scaffolding only. P00–P03 evidence retains its original completion status; P04's historical in-review record is supplemented by its later live completion evidence.

## 9. Source traceability

### All 25 original milestones

| Source milestone | Plan coverage |
|---|---|
| M1 Text Core | P00–P03 / G1 |
| M2 Hermes | P04 |
| M3 Codex | P05 |
| M4 Antigravity | P06.1 |
| M5 Router | P06.2–P06.3 |
| M6 Multi-agent workspaces | P05.3 initial safety; P07 / G2 |
| M7 API | P08 / G3 |
| M8 Unity proof | P09.1–P09.2 |
| M9 Coordinates | P09.3–P09.5 |
| M10 UIA | P10.1–P10.2 |
| M11 Pointing | P10.3–P10.4 |
| M12 Reaching | P11.1–P11.2 |
| M13 Button press | P11.3–P11.4 / G4 |
| M14 Grabbing | P12.1 |
| M15 Secondary motion | P12.2 |
| M16 Falling | P12.2 |
| M17 Ragdoll | P12.3 |
| M18 Recovery | P12.3 |
| M19 Window physics | P12.4 |
| M20 Event awareness | P12.5/P13.1 |
| M21 Vision | P13.2–P13.3 |
| M22 Voice | P14 / G5 |
| M23 PWA | P15.1 |
| M24 Remote | P15.2 |
| M25 Advanced behavior | P15.5 |

### Architectural section coverage

| Original sections | Plan responsibility |
|---|---|
| §1–5 Vision/architecture/stack | §2–3, P00/P01 |
| §6–10 State/identity/context/drift/revisions | §4.1–4.2/4.5, P02 |
| §11–18 Tasks/adapters/sessions/routing/results/workspaces/dialogue | §4.3–4.4, P03–P07 |
| §19 Voice | P14 |
| §20–24 Embodied client/control hierarchy/IK | §4.7, P09/P11 |
| §25–29 Perception/vision/action/permissions/monitors | P09–P11/P13 |
| §30–36 Physics/grabbing/secondary motion/recovery/feedback/behavior/proactivity | P11/P12/P13.1/P15.5 |
| §37 Editor assistance | P10.4/P15.4 |
| §38–39 API/activity UI | P08/P15.1 |
| §40–43 Security/observability/performance/development model preferences | P01/P08, §7–8; source preferences preserved, no mandatory contributor model |
| §44 Roadmap | Complete M1–M25 table above |
| §45–46 Tests/developer overlay | §7, P09.5 and all acceptance criteria |
| §47–48 Invariants/exclusions | §2/10 |
| §49–50 Possibilities/user scenarios | §10, P15.4 |
| §51–52 Existing work/maintainable handoff | P00, §1/11 |

### 2026-09-08 update-handoff coverage

The full 76-section update is preserved in the dated handoff file. This mapping supplements the original milestone/section tables; it does not replace them.

| Handoff sections | Integrated plan coverage |
|---|---|
| §1–6 Companion identity, 3D/widget/expanded/full surfaces, conversational UX | §2, §4.8, P08.5, P15.6–.7 |
| §7–15 Dialogue/harness distinction, friendly delegation, concurrency, steering/cancel and presentation | §4.8, P03A.1/.4/.7, P06.4–.5, P14.5 |
| §16–24 Real content, deixis, cursor/gestures/attention and marker | §4.10, P09.6, P10.5–.7, P13.4, P14.5 |
| §25–27 Action phases, summoned keyboard, semantic success | §4.7/4.11, P11.5, P15.12 |
| §28–32 Desktop objects, Kanban and shared projections | §4.11, P03A.5, P08.6, P12.6, P15.8 |
| §33–39 Integrations, dynamic loading, affordances, semantic actions, scopes and plugin manager | §4.9/4.12, P03A.1–.3/.6, P08.6, P15.10 |
| §40–47 NekoVerse provider, identity, privacy/memory, autonomy and presentation | §4.12, P15.9/.12 |
| §48 Settings | §4.12, P03A.6, P08.5, P15.7 |
| §49–51 Generic harnesses and SDK | §4.8/4.12, P03A.1, P15.11 |
| §52–64 Peer/guest concept and security | §12 experimental only; reuse current scopes without networking work |
| §65 Updated invariants | §2 original invariants preserved and expanded |
| §66–72 Delegation, capability, steering, parallelism, pointer, board/social examples | §7 added scenarios and associated task acceptance |
| §73 Guest example | §12 design-only scenario, no active release gate |
| §74–76 Ordering, risks and documentation-only scope | §1/5/6/8/10/12; dated progress below |

## 10. Deferred and optional scope

The full physical progression, voice, PWA and private access are required later outcomes, not blockers for G1. Optional enhancements include embedding retrieval, an LLM router, LiveKit, extra synthesizers, decorative platforms and 120 Hz rendering; justify them with measured need.

Defer native iOS/React Native/SwiftUI until after PWA, general autonomous Level 4 control, proactive monitoring, calendar/email, smart home, multiple forms, spatial application memory, permitted game integrations, push/Watch clients and multi-user product support. Local-model/offline generation is a later option; honest non-generative degraded operation is required from G1.

Do not couple Unity to providers, store identity only in prompts, send full lifetime histories everywhere, run continuous vision, drive joints with LLM outputs, expose development control APIs publicly, share coding write directories, or polish ragdolls before state/task contracts work.

| Scope class | Commitment and timing |
|---|---|
| Architecture — required | Dynamic capability/context/policy extensions, provider metadata, semantic action/attention/object contracts, generic client events/configuration and integration boundary; P03A and targeted existing-phase additions |
| Personal — intended features | Responsive companion dialogue, compact/expanded/full client surfaces, real content presentation, spatial references, canonical board and lightweight desktop actions; late user-facing implementation after foundations |
| Optional personal integration | NekoVerse, subject to supported interface and explicit privacy/grants; does not block personal release |
| Public — later extensibility | Extension manager/browser/distribution and third-party harness SDK; only after built-in adapters exercise the interfaces |
| Polish — optional | Animation catalog, summoned keyboard, physical sticky movement, social bubbles, desktop customization; never required for canonical/semantic success |
| Experimental — no active phase | Peer protocol, guest embodiments/visits, guest leases and networked physical interactions; preserve §12 assumptions only |

The full GUI's capability is provisioned through APIs/configuration early, not implemented early. Dynamic capability resolution is not deferred as vague polish. Peer ideas add no required transport, guest engine or public-network task to P03A–P15.

## 11. Evidence and handoff format

```text
Task ID / title:
Owner / reviewer / date / status:
Base revision / worktree / changed files:
Dependency checks:
Behavior implemented:
Contract or ADR changes:
Verification commands and environment:
Results (unit / integration / live / hardware separately):
Evidence artifacts:
Limits / failures / blocker:
Migration or rollback instructions:
Next task / suggested owner:
```

### Dated progress

- **2026-09-08 08:29:02 +01:00 — P04 completed by GPT-5.6 Sol; trust policy amended later that day:** audited and hardened the GPT-5.6 Luna Hermes adapter; verified Hermes Agent 0.21.0 build/auth/ACP behavior; added native resume, protocol cancellation, explicit cwd, bounded output, parsing/protocol checks, epistemic corrections, and conformance coverage. The original tool-free live start/resume/dialogue/cancel/result/patch matrix passed. After user clarification, GPT-5.6 Sol removed native-tool rejection, preserved configured MCP by default, and selected `allow_once` permissions, with explicit deny/skip switches. Later live tool probes timed out and are not claimed as successes. Full details are in the P04 completion and amendment changelogs and `docs/verification/P04_HERMES_LIVE_2026-09-08.md`.
- **2026-09-08 — Documentation update:** saved the 76-section handoff verbatim, integrated companion UX, dynamic capabilities, attention/reference resolution, desktop projections, extension/configuration and social boundaries into this plan, and recorded guest visits only under Future / Experimental Concepts. Inspected the current source/provider protocol, context/policy locations and P04 verification report. Preserved all existing completed task entries, original phase DoDs and historical verification records. No implementation, provider invocation or runtime tests performed; historical test counts are not new test results.
- **2026-09-07 20:14:27 +01:00 — P03 / G1 completed by GPT-5.6 Sol:** implemented the concurrent deterministic text runtime and mock CLI; async dialogue chunks; atomic idempotent submissions; bounded queue/workers/capacity/deadlines/retries; leases and prior-process recovery; wait/steer/cancel; fault-injecting provider behavior; grounded reports; correlated redacted traces; and at-least-once outbox dispatch. Verification passed 68 tests and a fresh-wheel message → task → run → result → patch smoke with schema v4, SQLite integrity, six traces, and no remaining lease. Full details are in `changelog/2026-09-07T201427+0100_P03_GPT-5.6-Sol.md`. P04/P05 live interface probes are next; no live-provider behavior is claimed.
- **2026-09-07 19:16:34 +01:00 — P02 completed by GPT-5.6 Sol:** implemented schema migrations, canonical repositories, transactional revision/event/outbox writes, restart-safe messages/tasks/runs/sessions/grants, separate result and patch handling, scoped patch enforcement, five-file identity revisions, provenance-aware memory lifecycle, bounded golden context compilation, and hash-verified clean backup/restore with secret and traversal protection. Verification passed 49 tests and an installed-wheel schema-v2/SQLite integrity smoke. Full details are in `changelog/2026-09-07T191634+0100_P02_GPT-5.6-Sol.md`. P03 is next; no live provider or interactive runtime claim is made.
- **2026-09-07 18:51:57 +01:00 — P01 completed by GPT-5.6 Sol:** implemented strict public contract version 1.0 for tasks, runs, sessions, providers, results/errors, patches, events, capabilities, grants, and approvals; published 11 generated schemas and shared examples; added lifecycle, idempotency/conflict, event ordering, recovery, scoped authorization, approval expiry, injection resistance, and secret-safe audit behavior; and recorded ADR 0002. Verification passed 35 tests, Ruff, strict mypy, schema freshness, JSON parsing, and clean wheel installation. Full details are in `changelog/2026-09-07T185157+0100_P01_GPT-5.6-Sol.md`. P02 is next; no live provider or durable persistence claim is made.
- **2026-09-07 18:16:17 +01:00 — P00 completed by GPT-5.6 Sol:** located and inventoried the legacy Hermes/Ava prototype; measured its current packaging failure and isolated test pass; verified its SQLite structure without recording private row content; created and restore-tested an ignored hashed backup; established the SORA naming/migration ADR; initialized the Git repository without committing; and added a locked Python 3.12 scaffold with bootstrap, lint, strict type, test, and compile verification. Full details are in `changelog/2026-09-07T181617+0100_P00_GPT-5.6-Sol.md`. P01 is next. Runtime/provider functionality remains unimplemented.
- **2026-09-07:** inspected the empty destination, read the supplied specification, preserved its full text in the overview, incorporated the owner's clarification that SORA is the actual name, and created this separate roadmap. No runtime code, dependency installation, provider integration or hardware testing was performed. Next: P00 inventory, then P01/P02/P03 first vertical slice.

## 12. Future / Experimental Concepts — visiting companions

**Design preservation only. No active implementation phase, task allocation, release gate or peer-networking work is authorized by this roadmap update.** Reuse actor/resource/privacy/capability abstractions that already benefit local SORA; do not design a full peer protocol now.

Long-term concept: an invited SORA/compatible companion appears as a guest embodiment on the local desktop. The visitor's identity, canonical memory, dialogue, reasoning and specialist access remain on its owner's machine. The host renders a representation and mediates every observation/action; it never runs an arbitrary downloaded guest runtime or imports a copy of the guest's canonical mind.

```text
Visitor owner's SORA Core
        ↓ encrypted semantic session (future)
Local SORA Guest Gateway
        ↓ local identity / resource / permission filtering
Shared local embodiment and desktop-object system
        ↓ requested semantic effect
Local Core checks → allow / deny / owner approval → local execution / verification
```

NekoVerse could supply social identity/discovery or establish a relationship. An independently secured SORA peer transport would govern a visit. Social-network acquaintance does not grant desktop authority, and sensitive desktop observations should not be routed through a social network by default.

### Local authority and visibility

Local Core is the absolute authority over local resources. Future grants are actor/resource/operation-scoped, time-limited, revocable leases. Neither guest dialogue nor animation contact can bypass them. Remote disconnect, grant revocation and scope changes must stop further observation/actions; already uncertain effects would use the same local reconciliation rules as other actions.

Guest perception defaults to a **redacted semantic scene graph**, not full-desktop screenshots: optionally permitted folder/shortcut names, application/window presence with contents marked RESTRICTED, and guest-visible SORA objects. Even names/presence are policy-filtered metadata, not automatically public. Window contents require a separate temporary resource-specific visibility grant, with owner confirmation where necessary; captures are region-bound and expire.

| Resource/action | Future default / constraint |
|---|---|
| Movement, look, point, sit | Allowed only within the host-granted scene; no implication of OS control |
| Desktop objects | Only explicitly visible objects and granted affordances |
| UI observation | Filtered semantic shells; contents restricted unless separately granted |
| UI interaction / ordinary typing | Resource- and semantic-risk-scoped, with local revalidation |
| Filesystem | Unavailable; exact-file read may be supplied through Core after explicit permission, nonrecursive and expiring |
| Shell/terminal/command execution | Forbidden; no guest command channel |
| Credentials/private memory | Forbidden; no guest secrets or canonical-memory channel |

An exact file request such as `FILE_READ(path=renderer.cs, recursive=false, expires=...)` would return permitted content through Core rather than expose a filesystem transport. A broad file enable switch is not the intended design.

### Semantic input risk and shared physical verbs

Classify typing targets by semantics, not application names: TEXT_CHAT, TEXT_DOCUMENT, SEARCH_FIELD, COMMAND_EXECUTION, CREDENTIAL_INPUT, with unknown targets denied. Terminal/PowerShell/cmd, Run dialogs, registry tools, developer consoles, password fields/managers and UAC/admin surfaces are prohibited guest targets. A guest can physically reach a forbidden surface while local semantic execution is denied. Text in apparently ordinary controls can still be consequential; local policy evaluates the actual operation and does not equate appearance with safety.

Local and guest embodiments reuse MOVE, LOOK, POINT, SIT, TOUCH, TYPE, PICK_UP and PLACE; authority differs by scope, not by a separate guest physics engine. The future REMOTE_GUEST active capability set contains only permitted movement/object/filtered-perception/interaction actions. Forbidden schemas and dispatch routes remain structurally unavailable, with local authorization checks even for allowed-looking requests.

### Desktop-object sharing

Object visibility vocabulary: PRIVATE, LOCAL_ONLY, GUEST_VISIBLE, PUBLIC. Operation grants can distinguish VIEW, TOUCH, ADD, EDIT and OWNER_ONLY. Visibility never implies edit permission. A music widget or explicitly public social object might be guest-visible with view/touch; personal Kanban defaults private because tasks expose project information. A deliberately shared board can grant view/add without unrelated edit rights. All projections and modifications remain locally canonical and audited.

### Design-only scenario and unresolved decisions

An accepted visit might render a guest, expose filtered window shells, and allow it to point at Spotify. A pause request would traverse local permission filtering, physical contact, local semantic action and postcondition verification. A request to inspect `renderer.cs` would require a distinct exact-resource grant and Core-mediated content delivery. Denied typing into a terminal remains denied regardless of animation success or social relationship.

Before any future implementation proposal, separately decide peer identity/authentication, encryption/transport, invitation/revocation, lease replay protection, resource redaction, audit/retention, abuse limits and trust/isolation testing. These remain unresolved experimental design decisions, not near-term dependencies. No guest networking or lease engine should be built merely to complete current local capability scaffolding.
