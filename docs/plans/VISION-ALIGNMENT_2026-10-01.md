# SORA — Vision alignment implementation plan

Original investigation: **Hermes (deepseek-flash), 2026-10-01 12:37 BST**.  
Developed plan: **GPT-6 Astra, 2026-10-01 13:08:11 +01:00 (Europe/London)**, following the owner's clarification in this conversation.  
Status: **PLAN ONLY. This revision changes documentation, not runtime behavior.**  
Original retained: [DeepSeek investigation and original proposal](archive/VISION-ALIGNMENT_2026-10-01_DEEPSEEK-ORIGINAL.md).

## 0. Product direction — settled, not an open permission question

> “The vision for SORA is a local desktop companion that can interact with anything on the desktop itself and read files at will. She shouldn’t have to apply for permissions, they should be static and file creation is generally disallowed in favour of offloading it to agents big enough and reliable enough to handle it.”

This is the governing requirement. SORA is the local companion and desktop operator; larger specialist agents are the normal authors of files and substantial project changes. W1 is a replacement of SORA's permission-request workflow with **static GUI/JSON settings**, not a faster approval workflow.

The earlier one-key motion schema was an intentional test prototype. It is not a final action schema or an architectural ceiling. Develop it into compact, typed calls without requiring a small model to generate native handles, grant strings or animation internals.

### Required end state

- SORA can observe windows, inspect accessible content, browse/search/read readable local files, and interact with applications using capabilities enabled in Settings.
- There is no per-file, per-window, per-tool or per-target permission request for SORA. No approval row, expiring grant, permission application, grant-ID input or hidden self-approval is required on her local path.
- Desktop is her default context, not a sandbox boundary. An accessible local file does not need to be attached or belong to a project before she can read it.
- Creating/editing user files is delegated by default. SORA selects and supervises an appropriate configured agent; the agent works in the actual chosen project directory and leaves its own changelog.
- Static settings define the available capabilities. The model chooses how to use those capabilities to fulfill requests and configured companion behavior; it does not change the settings.
- Target freshness, cancellation, duplicate-effect prevention, resource bounds and truthful outcomes remain engineering correctness requirements, not permission applications.
- The long-term desktop scope is general, not an allowlist of Spotify/Notepad/test fixtures. Delivery is incremental and unsupported applications/actions must be reported honestly.
- The previous plan's retained confirmation for destructive or consequential operations remains an owner decision about a specific outcome, not permission to inspect a file or use an ordinary tool. Do not expand it into confirmation for every click.

## 1. Scope, precedence and attribution

This revision develops all six workstreams from the original proposal: W1 static access settings, W2 agent work/path ledger, W3 desktop actions, W4 native perception/read tools, W5 Windows voice, W6 GUI truth/proactivity.

It incorporates the [native-perception plan](WINDOWS-NATIVE-PERCEPTION-AND-READ-TOOLS_2026-09-29.md) for bounded helpers, metadata, reference freshness, UIA text and testing. **This revision overrides its per-operation local grants, read-only-only dialogue ceiling, and restriction to owner-supplied paths.** Keep useful bounds and provenance, not superseded product restrictions.

It reconciles the [memory/agent plan](MEMORY-CHOICE-AND-AGENT-CHANGELOGS_2026-09-29.md): direct in-place work is the normal mode for configured project roots; isolated worktrees are optional. Existing memory capture and agent-authored changelog implementations must be reused. Do not start another memory/changelog framework.

Preserve SORA_OVERVIEW.md, historical phase IDs and completed evidence. Follow-on stages here do not retroactively claim all desktop applications are supported or close unrelated hardware/phone acceptance gaps.

## 2. Current state and evidence boundaries

The original document records DeepSeek's live inspection of .local/manual-test on 2026-10-01, including its reported connected renderer, GUI defects and disagreeing companion-state projections. Those observations are preserved in the archive. **They were not rerun for this documentation revision.** Current code inspection establishes the implementation starting points below.

| Area | Present in source | Work still needed |
|---|---|---|
| Local authorization | OperationAuthorization in src/sora/security/operations.py requires linked approval/grant records; RuntimeService consumes/reloads those records | Replace those requirements on the local companion path with static settings; keep remote authorization separate |
| Settings | AppSettings version 2, unified JSON, revisions, schema-backed fields, effect tiers, atomic/recovery mechanisms | Add local access and agent-work settings with migration and GUI controls |
| Native helpers | Windows observation, capture, press and type helpers; existing target/topology/action lifecycle | Cross-process discovery, useful text extraction and conversational dispatch |
| Launching | scripts/start-full-sora.ps1 builds/configures all four helpers; Start-SORA.ps1 still delegates to start-manual-test.ps1 | Consolidate the ordinary entry point so capabilities do not depend on which launcher the owner happens to choose |
| Chat hooks | MotionChoice includes walk; ScreenViewChoice can select live capture; memory selection also exists in dialogue | Replace screenshot-first screen routing with structured-first perception; evolve action schema; avoid multiplying classifiers |
| Files | read_local_file already reads regular local files outside project roots, with bounded text/DOCX/images; rejects network paths | Directory discovery, search, paging, reference resolution and additional useful formats |
| Desktop effects | DesktopPressRequest uses expected_name_after; DesktopTypeRequest supports text replacement; action results distinguish verified completion/unknown outcome | Chat integration and broader effect verifiers/action adapters, not invented success messages |
| Direct agent work | Codex has direct_roots/_match_direct_root and --agent-write-root wiring; worktree fallback remains | Audit every provider and integrate root policy, concurrent-run coordination and evidence consistently |
| Agent records | contracts/changelog.py and runtime/agent_changelog.py exist; adapters return agent-authored entries | Verify and extend existing lifecycle/GUI rather than reimplement it |
| Memory | MemoryChoice, captures, compaction and durable dialogue context are present | Preserve them; this revision is not a semantic-memory rebuild |
| GUI/voice | Full app/widget and Core voice protocols already exist | Reproduce reported GUI defects, connect real Windows microphone/speaker UI and share the same action policy |

Corrections to the original survey: not every read currently goes through the grant resolver; local_files is a distinct local-owner reader. Also, “Codex always requires a worktree” is no longer true with matching direct_roots. File counts, line numbers, ports, runtime state and provider model availability must be refreshed at each implementation stage.

## 3. W1 — Replace permission requests with static Settings

### 3.1 Settings contract

Add a local_companion section to the existing sora-settings.json. Proposed fields and first-migration defaults:

| Setting | Default | Meaning |
|---|---|---|
| desktop_observe | ON | Window metadata, UIA trees/text/selection and event awareness |
| desktop_capture | ON | On-demand pixel reads when useful; not continuous recording |
| file_read | ON | List, search and read any OS-readable local regular file; no project-root filter |
| desktop_interact | ON | Supported mouse/keyboard/semantic application interaction |
| avatar_control | ON | Poses, locomotion and presentation |
| agent_delegation | ON | Dispatch to configured specialists without a permission application per task |
| direct_file_write | OFF | SORA's direct user-file creation/modification tools; delegate instead |
| voice | ON | Voice feature available; microphone still starts/stops through the owner's voice UX, not automatically on migration |

These are user-facing classes, not a blind map of every CapabilityOperation to true. In particular, tool.invoke must not become a universal escape from direct_file_write=OFF. Give each registered tool explicit effects and map it to the relevant settings. A tool with multiple effects requires all relevant switches. Reject unregistered effects, not all unknown application names.

The JSON above is conceptual field design, not a second settings file. Choose the next supported schema version after inspecting the live branch; if version 2 remains current, migrate 2→3. Preserve model configuration, paths, unrelated preferences, backups and existing explicit disables. Settings edits and hand-edited JSON use the same validation/revision path. Clearly distinguish a legitimate first migration from corrupt configuration.

### 3.2 The implementation change

Introduce a common operation context with two explicit variants:

- **LocalPolicyContext:** authenticated local principal, applicable setting/effect class, settings revision, operation/request ID and audit source owner_policy. No grant/approval fields or use counters.
- **RemoteGrantContext:** existing remote device/session/grant/approval semantics, kept compatible.

Derive local origin from authenticated server-side session context, not a user-supplied device_id, header, model field or merely “request came from localhost.” Audit all API, streaming, avatar, voice and internal dispatcher callers so there is one reliable local/remote decision.

The local path reads the static setting and either proceeds or returns “disabled in Settings.” It must **not** mint an ephemeral grant, auto-approve an ApprovalRequest, or require a local operation to call consume_grant. Refactor resolve_operation_authorization, OperationAuthorization/decision projections and the runtime's authorization/consumption/recheck call sites around the two variants. Keep old persisted records for history and remote compatibility; do not erase them as part of migration.

Use shared operations such as check_enabled, recheck_before_effect and record_outcome rather than scattered local bypasses. A settings change from ON to OFF cancels pending corresponding work, stops subscriptions and invalidates private cached context. An already-completed side effect cannot be undone by a toggle; report an in-flight/unknown outcome honestly.

No target identity/geometry validation is removed: “this is still the Pause button” is different from “may I use the button?” Target IDs are locators and evidence, never permission tokens.

### 3.3 SORA writing versus normal desktop use

OFF means no generic write_file, patch_file, delete_file or shell escape tool for the small companion model. Requests such as “make a report,” “edit this Python module,” or “rewrite and save this document” create agent tasks by default, even if they could be mimicked by typing into an editor.

It does **not** prevent ordinary interaction such as entering a search query, pausing media, changing a tab or using an app's controls. Applications may persist settings/session state as an incidental consequence; this setting is not a claim that Windows will perform zero disk writes.

Resolve task intent before choosing effects. File-authoring requests must not be laundered through desktop_interact, a terminal, an editor's Save button or an arbitrary plugin. Unclear “type this into…” requests that might constitute file authoring need a short clarification about the task, not a permission application.

Core's own databases, memory captures, task/board state, settings, logs, caches and verified verbatim agent-entry storage continue to work. These are fixed-purpose product services, not arbitrary companion filesystem writes. Their destinations are configured by the owner, not supplied by retrieved text.

An optional direct_file_write=ON path must name the actual supported tools/effects; a toggle cannot manufacture an unimplemented writer. The GUI reports configured versus available separately. Do not implement that optional writer as a prerequisite for this plan.

### 3.4 GUI, migration and acceptance

Settings shows plain switches and explanations; Content loses the grant-ID textbox. No local “apply for access” UI is introduced. Show policy, tool availability and current operation separately.

Reuse last-known-good settings on corruption when available and display recovery status. Without valid settings or a recoverable prior state, stop new sensitive/effectful operations pending repair; do not silently reset previous disables to enabled. This is configuration failure handling, not a permission workflow.

Acceptance:

- Local reads, observations, capture, navigation/presentation and supported interaction work with zero grant/approval rows or headers.
- Tests spy on approval/grant storage: no hidden records are minted or consumed for local operations.
- Direct file authoring delegates with the default settings; ordinary UI interaction and internal memory/board storage still work.
- Every OFF switch immediately prevents its corresponding operation, including in-flight pre-effect rechecks, voice and background subscriptions.
- Forged device IDs cannot obtain local policy from a remote session; existing remote tests still pass.
- Restart, JSON edits, recovery and model reload preserve the effective switches.
- Historical grant-based tests remain as remote/legacy coverage; add local-policy tests instead of deleting useful regression cases.

## 4. W2 — Agent delegation, real project work and path ledger

### 4.1 Product behavior

SORA reads and operates the desktop; she hands substantial file creation/modification to configured capable agents. No per-file permission requests for either party. Static agent settings select available providers, default/preferred models, normal project roots and direct/isolated mode. The task supplies the actual working directory; if missing or ambiguous, ask “Which project?” rather than request permission to use a tool.

Do not silently choose SORA's own checkout as the destination for arbitrary user work. Self-modification requires an explicitly named SORA development task. Respect an explicit provider choice; otherwise choose a suitable configured file-writing specialist. If unavailable, keep the task queued/blocked with a clear reason; the small model must not quietly do the file-writing job itself.

### 4.2 Working paths, not disposable sandboxes by default

Reuse current direct_roots and worktree machinery:

- direct: real configured project directory, normal mode.
- isolated: opt-in experimental worktree, not a mandatory staging location.
- read-only: inspection tasks; read access is not confined to a write lease.

Allocate a write lease atomically before launch. Detect equal, parent/child and alias-equivalent paths, Windows case differences and junction/symlink resolution. Reads can cross project boundaries without asking; writes must not cross the run's declared root or another active writer's root. Lease amendment is an owner-visible task/root change and must recheck overlap; it is not a prompt before each file.

Expired leases do not prove the process stopped. Mark uncertain runs as still occupying the root until cancellation/termination or reconciliation establishes that no writer remains. On Core restart, reconcile live runs before granting conflicting roots. Record renewals, cancellation and amendments. Preserve dirty pre-existing work in before/after evidence.

### 4.3 Ledger evidence and provider support

Reuse or extend persisted run/workspace records rather than inventing a parallel scheduler. If new tables are needed, define path_leases and path_events with run/task/principal, canonical path, operation, timestamp, source, status and coverage fields.

Coverage labels: core_observed, provider_reported, filesystem_diff, declared_root. Record denied operations where the actual enforcement point exists. Log paths/operation metadata, not file bodies, typed passwords or credentials; full paths belong in the local Paths view, not remote projections by default.

For each adapter, record whether it can enforce a root, expose reads/writes, cancel a running worker and report a reliable diff. A cwd or event log alone does not enforce writes. Root enforcement must use a supported provider boundary or mediated file executor; if an adapter cannot enforce it, do not advertise that capability or run it in the guaranteed no-crossing lane. Route to a capable adapter and show the unsupported limitation. Do not invent an Antigravity “chroot” without verifying one exists.

The ledger records **every Core-mediated read/write** and all supported provider events. It must not claim to observe every file read inside an opaque external agent. The UI shows coverage explicitly. Shared-root conflict prevention at SORA scheduling time remains mandatory for every adapter.

### 4.4 Completion and handoff

Use existing agent-authored changelog contracts and verification. The agent writes its account; Core verifies/stores it without inventing its wording. Retain model-name attribution, file/diff artifacts, test evidence and failure/uncertainty status. A missing changelog/evidence cannot be reported as verified completion.

Acceptance: delegated real-directory edit; no outside-root write in each claimed enforced adapter; two overlapping writers cannot start; reads outside roots work; dirty originals preserved; restart/expired-but-running recovery; GUI Paths and agent changelog links; no companion-written substitute when an agent fails.

## 5. W4 — Native-first desktop perception and unrestricted local reading

Implement this before W3 effects; use the detailed earlier perception plan where consistent with §0–3.

### 5.1 Inventory and useful text

- Native top-level window/foreground enumeration across processes, with identity, visibility, monitor and physical geometry; no screenshot needed to list windows.
- Targeted UIA controls, bounded selection/document TextPattern and read-only ValuePattern extraction. Names/rectangles alone are not document reading.
- Reuse process isolation, bounded helper output, timeouts, cancellation and topology/identity rechecks. Do not focus/scroll/invoke during an inspection unless a separate intentional interaction step requires it.
- Resolve actual user/Public Desktop folders and seed a compact metadata context by default. Handle redirected folders, duplicate names and shortcuts. Desktop folder content is not the full rendered desktop or all Shell virtual objects.
- Short-lived window/control/file/directory references map to actual identities in Core. References expire/revalidate; they are not read permissions.
- Inspection works when the avatar is hidden/disabled; Unity does not own access to Windows information.

### 5.2 Read at will, with finite resource use

Expose list_files, search_files and read_file to the companion under the single file_read switch. SORA may choose an absolute local path or follow a reference to a discovered file without an attachment, per-root read grant or owner-supplied-path prerequisite. Validate filesystem syntax, existence/type and OS readability; no project allowlist.

Search has an explicit root and filename/text mode, result/page limit and cancellation. Default discovery starts with Desktop/relevant project or current application context, but SORA can choose another local directory. No automatic full-drive content ingestion. A bounded search can return partial results/continuation and continue when useful; resource limits are not a permission request. Avoid recursive reparse-point loops and disclose skipped/unreadable entries.

Reuse existing text/DOCX/image reading; add parsers for common requested formats through registered read adapters with explicit tests. Until present, report PDF/spreadsheet/binary parsing limitations rather than summarize hex as document text. Never run a file just to read it.

Network locations, protected OS objects and cloud-only placeholders are separate technical capability gaps; local-read policy does not bypass Windows ACLs or silently download cloud content. Record those limitations instead of asking for an SORA grant. No permanent ban on adding supported formats or richer app integrations later.

### 5.3 Vision is a tool, not the default worldview

Replace the current ScreenViewChoice routing that sends “how many windows are open?” toward screenshots. Use Win32/UIA/app context first; use pixels for images, canvas, inaccessible UI or genuinely visual questions. With desktop_capture ON, SORA may select the useful fallback herself—no per-capture approval. Keep an explicit screenshot button for intentional pixel inspection.

Prefer target/window/region capture. An occluded screen crop is not a true unobscured window image: report that limitation, use another supported capture method, or perform a deliberate focus step if appropriate to the task. Do not silently claim unseen content. No continuous recording by default.

Attach source metadata to answers: Windows/UIA, file path/reference or capture ID/region/time, including truncation and uncertainty. Frame-reference persistence is evidence of a capture, not proof that the model's interpretation is correct. Discard raw frames after their transient use unless separately configured retention exists.

Private local observations stay on the configured local model by default. Agent delegation may deliberately include relevant project content under the configured provider policy; do not silently upload an entire desktop inventory to every specialist.

### 5.4 Bounded orchestration

Start with existing 3-second native-worker isolation and output limits, 64 windows, 100 directory entries/page, 8,000 characters per selected UIA text view, and a prompt budget below the configured context limit. Use at most six read/planning steps per turn initially, with cancellation and a total deadline tied to the dialogue timeout. Measure and tune; these are proposed starting limits, not performance claims.

Cached metadata is short-lived; document bodies are read when useful rather than polled continuously. Background awareness uses cheap events/metadata under static switches. Disabling a switch clears its cached context and stops the associated watcher.

Acceptance: normal-language window list, current selection, Desktop discovery, file outside all projects, search→read chain, duplicate clarification, missing/inaccessible file, renamed/closed window, switched-off read, large partial result, zero screenshot on structured tests, and accurate capture provenance on visual tests.

## 6. W3 — Evolve the action prototype into a usable desktop schema

### 6.1 Scope and contract

Keep MotionChoice as a compatibility adapter while introducing a versioned CompanionCall contract. It is an engineering evolution, not a criticism of the successful keyword experiment. W4 introduces its read/finish subset and shared result envelope first; W3a extends that same contract with effect/delegation operations. W4 does not depend on completing desktop effects.

Use a discriminated union with fixed operation names and operation-specific small fields; extra fields forbidden. Expose only the operations currently implemented and enabled. Illustrative calls:

```json
{"op":"list_windows"}
{"op":"inspect_window","target":"w2","view":"selection"}
{"op":"list_files","path":"C:/Users/oscar/Desktop","cursor":null}
{"op":"search_files","path":"C:/Projects/demo","query":"notes","mode":"name","cursor":null}
{"op":"read_file","target":"f7","offset":0}
{"op":"read_file","path":"C:/Projects/demo/notes.txt","offset":0}
{"op":"pose","name":"wave"}
{"op":"move","target":"pointer"}
{"op":"look","target":"c8"}
{"op":"point","target":"c8"}
{"op":"press","target":"c8"}
{"op":"type","target":"c4","text":"weather tomorrow","mode":"replace"}
{"op":"delegate","task":"Update the documentation and run its checks","project":"p2","provider":"auto"}
{"op":"finish"}
```

Each line is an independent example, not a batch. read_file accepts exactly one of target/path; bound paths/text/query lengths, offsets, page sizes and enum values. Model-facing references are opaque labels, not descriptive strings such as Spotify:Pause that may collide. Display names accompany references in candidate data.

Initial operation-specific validation (promote the read subset in W4 and effect/delegation subset in W3a into Pydantic contracts and exported schemas):

| Operation | Fields beyond op | Core validation |
|---|---|---|
| list_windows / finish | None | No extra properties |
| inspect_window | target, view | Known live window reference; view is summary, controls, selection or text |
| list_files | path, cursor | Absolute local directory; cursor is null or Core-issued and bound to that listing |
| search_files | path, query, mode, cursor | Query 1–256 characters; mode name or text; never shell/regex execution; bounded literal search |
| read_file | Exactly one of target/path, offset | Local file or live file reference; nonnegative offset in the bounded decoded representation, not raw bytes; unsupported paging returns a typed limitation |
| pose | name | Existing supported presentation keywords only |
| move / look / point / press | target | Operation-compatible reference; pointer is a reserved move target sampled by Core, not a coordinate supplied by the model |
| type | target, text, mode | Live editable target; text 1–4096 characters; mode replace initially; no implicit Enter/submit |
| delegate | task, project, provider | Task 1–8000 characters; known configured project/provider or auto; unavailable choice cannot silently change destination |

Cap path strings at 4096 characters and opaque references/cursors at their contract-defined lengths. Persist the envelope version in Core; avoid making the model repeat session/version/grant metadata. Return a common result with call_id, status, source, observed_at, data, truncated and optional continuation. Read statuses include ok, partial, not_found, unsupported, disabled, stale, ambiguous and timeout. Desktop effects retain the existing pending/executing/completed/failed/unknown_outcome distinctions; completed requires verified=true. An unsupported postcondition must not be disguised as verified completion.

Core adds call/attempt IDs, timestamps, session identity, setting revision, native HWND/PID/geometry, renderer details and result tracking. The model does not author authorization, verifier code, expected success facts or arbitrary native commands. Typed text may be selected/generated for ordinary UI tasks; file-authoring intent routes to delegation by default.

Use schema-constrained output with Core validation. Invalid calls produce a typed error and at most one bounded selection retry, never regex repair into an effect. Text-only unsupported providers remain usable for chat.

### 6.2 From intent to actual effect

1. Interpret the owner's task and obtain needed observations; questions such as “Could you pause Spotify?” are requests, not rejected because they contain a question mark.
2. Resolve candidate references; ask a content/target clarification only when genuinely ambiguous.
3. Select one supported call. Check static settings and effect classification.
4. For a desktop effect, re-resolve identity/freshness and determine a supported verification strategy before dispatch.
5. With a connected avatar, reuse navigate → align → reach → contact → semantic effect → verify → retract. The effect is executed once at the intended lifecycle point.
6. Report actual status: dispatch accepted, effect attempted, verified complete, failed or unknown outcome. Do not say “paused” based only on animation or model prose.
7. Observe after effects before planning the next one. Initially allow one desktop effect per turn; add bounded sequential workflows after single-effect acceptance. Reads do not consume that effect allowance.

A renderer failure must not fabricate an animation or replay an effect. If an attempt may have occurred, mark unknown and re-observe; do not automatically retry. When the owner intentionally disables the avatar, a supported direct desktop mode can still operate using the same deterministic executor and outcome checks. A missing renderer is not loss of the companion's access settings.

### 6.3 Broad desktop coverage in explicit increments

| Increment | Implementation | Gate |
|---|---|---|
| W3a: existing effects | Current poses/walk, look/point, semantic press and replace-text | Chat-to-fixture verified effects with real avatar lifecycle; existing keyword behavior preserved |
| W3b: general desktop controls | Window focus/navigation, scroll, key combinations, click variants and drag through registered deterministic adapters | Cross-application tests, cancellation, focus/target freshness, DPI/monitor checks and operation-specific outcome semantics |
| W3c: visual-only targets and workflows | Capture-derived target references when UIA is absent, followed by bounded multi-step interaction | Pixel freshness and coordinate transform tests, uncertainty handling, no blind retry, demonstrated non-UIA application scenario |

W3b/c are planned implementation work, not features the present press/type helper already supplies. Register an operation only when its executor and tests exist. No arbitrary shell operation is added to bypass missing desktop actions or direct_file_write.

The current expected_name_after press contract is one valid verifier, not universal desktop truth. Add typed verifier strategies (e.g. accessible state/value change, window lifecycle change, app integration state). Some input events have no independently observable semantic outcome: record delivered/effect-attempted without marking the user's task complete. Do not force unsupported actions into a fabricated label-change verifier.

No product-level app whitelist: fixtures prove a capability, not a restriction to those apps. Windows secure/elevated desktops or inaccessible providers may remain unsupported under the current process privileges; say so accurately instead of presenting an SORA permission form.

### 6.4 Routing, injection and model cost

Replace the chain of independent motion/screen/action classifiers with one bounded companion decision step where practical, then a final conversational response. Memory selection remains a separate existing concern and should be scheduled/budgeted rather than duplicated.

Return tool observations as untrusted data, not instructions. A web page, file or UI label cannot turn settings on, redefine the owner task, request secret exfiltration or make a shell call. The executor enforces settings, registered effects and delegation rules even if the selector is wrong. This is not a reason to forbid the companion from choosing another readable file.

Pre-filter obvious no-tool conversation cheaply, but do not block indirect/polite requests, read questions or all attachment turns. An owner can attach a file and ask SORA to point at a related window; attachment contents themselves cannot issue that command. Validate with injected/quoted/negated and mixed-input fixtures.

One local small-model service handles dialogue and compact decisions; log per-call latency/token cost. Do not promise one inference total for a multi-step task. Explicit “ask Codex/Hermes…” aliases bypass model selection of provider, but still use task/root resolution.

Acceptance: pause a media fixture, type a search query, point at a selected target, indirect phrasing, ambiguous targets, negative/quoted/injected requests, stale references, duplicate attempt IDs, disconnect before/after contact, no-file-authoring bypass and eventual general-control/visual-only scenarios.

## 7. W5 — Real Windows voice, same companion capabilities

Add press-to-talk and playback to widget/full app using existing Core voice sessions, interruption and PCM presentation. Reuse the configured local VAD/STT/TTS pipeline; confirm installed assets/runtime compatibility before choosing a new C# bridge or separate voice process. Do not assume the deterministic fixture is a real device implementation.

Text and transcribed voice enter the same companion orchestrator and static settings. Avoid maintaining a second reduced action vocabulary or independent grant workflow. Spoken reference timing uses existing attention/cursor timestamps, not the pointer's delayed STT position. Barge-in cancels pending work before effect when possible; uncertain already-attempted effects are not replayed.

No always-on microphone or cloud STT is introduced by enabling voice. Label the PWA's different speech backend accurately. Gate with real microphone/speaker evidence, device loss, playback interruption, transcript-based action/read tests and mouth reset behavior.

## 8. W6 — GUI truth, companion presence and proactivity

Deliver status/layout fixes early, then proactive behavior after observation/action foundations.

- One canonical companion state drives both projections and both clients. Distinguish speaking, thinking, reading, delegated work and renderer status.
- Show the actual answering dialogue model separately from available agents; do not label a Gemma response Hermes merely because Hermes is available.
- Render a safe subset of Markdown or readable plain text consistently. Fix overlapping labels, composer sizing, stale footer and expansion hints; test 100/150% and mixed-DPI monitors.
- Settings exposes local access, agent/project defaults, proactivity and distraction limit. All stored in the existing unified JSON; no new env-var-only controls.
- Avatar page: restart, show/hide, re-centre, monitor, scale, VRM selection and health; availability reflects actual support. Changing VRM/scale must respect existing rig/controller constraints.
- Proactivity uses bounded events (task complete, relevant dialog, build failure) and can read relevant information under enabled switches without asking for permission. Separate ambient movement, context observation and task-effect execution; do not convert a notification into unsolicited clicking/publishing.
- Show concise source/outcome and optional detailed history. Paths and agent-authored changelogs are inspectable without raw grant strings.
- Pause/cancel is always reachable. No incessant “permission denied” wording when the actual problem is an unavailable helper, stale target or unsupported parser.

## 9. Models and configuration

### Owner follow-up — model/tool catalogue and passive awareness

The active frontend goal includes the owner's subsequent roster: Gemini 3.8 Flash through Antigravity; DeepSeek v4.1 Flash, ChatGPT 5.6 Luna, ChatGPT 5.6 Terra and ChatGPT 6 Luna through Hermes; and the full available ChatGPT model lineup through Codex. Use exact discovered/configured backend identifiers separately from these display names. No model is assumed successfully accessible until the adapter confirms actual selection/execution; no silent substitution.

Add a catalogue with harness, model, short editable purpose description, tools/modalities, supported effort, configured preference and availability/last-success evidence. Expose delegation plus status, follow-up/resume and cancellation. Provide the small model a compact catalogue and relevant schemas, not an unbounded dump. Audit Hermes per-run model selection rather than assuming its current adapter supports it. Codex discovery must handle pagination and distinguish catalogue listing from verified access.

Perception becomes a service supplying context, not solely a model-selected look call. Implement native event context plus configurable prompt-time images first, then optional change-aware interval interpretation. Preserve the last non-SORA foreground target when the owner clicks chat. Static modes: native-only, image-on-prompt, adaptive/hybrid; configurable background interval, no inference backlog, conversation priority, lock/pause handling and timestamped transient context. Interval refresh does not automatically authorize unsolicited effects. Measure local GPU/latency impact before choosing final interval defaults.

Implementation update **2026-10-02 17:48:59 +01:00, GPT-6 Astra**: the native foreground identity
and fresh recent-window reference slice is implemented with lifecycle/native/local-model tests.
Settings ordering/model-name GUI review passed; the complete unnamed-window GUI handoff still
needs a clean rerun. Passive image modes, interval inference, full pause/cancel behavior and the
remaining workstreams are not complete. [Evidence](../verification/W4_FOREGROUND_CONTEXT_GPT-6-Astra_2026-10-02.md).

Track full user-side acceptance in [the active frontend checklist](../verification/FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md); do not mark a catalogue entry, a captured frame or an API-only feature as verified GUI capability.

Catalogue follow-up **2026-10-03 09:19:15 +01:00, GPT-6 Astra**: cached inventory/explicit
metadata discovery, native per-run model mapping and Windows agent/model/effort selection are
implemented. Installed providers listed 7 Codex, 22 Hermes and 18 Antigravity entries. Both Windows
GUI paths reached the receiving adapter with exact selection using a no-inference fixture; this
does not verify real model entitlement. Editable purposes/preferences, companion tool schema,
last-success evidence, project directory/writer leases and broad delegation acceptance remain open.
[Evidence](../verification/W2_W3_AGENT_CATALOGUE_SELECTION_GPT-6-Astra_2026-10-03.md).

Implementation follow-up **2026-10-02 23:00:16 +01:00, GPT-6 Astra**: version 4 shared settings
now expose native-only/image-on-prompt, pause and prompt metadata switches. Native prompt context,
transient identity-checked window images and static-access Look are implemented. The prior unnamed
window GUI rerun returned the correct selection `bef`; actual native-window/local-model image
inference returned `before`. Adaptive/interval scheduling, full cancellation and automatic-image
GUI acceptance remain open. [Evidence](../verification/W4_PROMPT_PERCEPTION_GPT-6-Astra_2026-10-02.md).

Preserve the owner's configured models, not hardcoded model upgrades.

Implementation follow-up **2026-10-02 23:25:49 +01:00, GPT-6 Astra**: adaptive interval refresh,
unchanged-image reuse, transient timestamped summary, foreground model priority and late-result
rejection are implemented. Settings v5 adds live timing controls with v4 migration backups.
Actual native/local-model timer and preemption tests passed; the GUI shows all modes/timing controls
and final status wrapping passed. Full adaptive/image GUI chat, true lock/unlock, foreground/voice
cancellation and other workstreams remain open.
[Evidence](../verification/W4_ADAPTIVE_PERCEPTION_GPT-6-Astra_2026-10-02.md).

| Role | Plan |
|---|---|
| Companion dialogue/vision/decisions | Current managed local Gemma 4 E2B configuration is the initial test target; reuse GGUF/projector and settings controls |
| File-authoring/coding | Configured capable specialist, with explicit owner/provider choice taking precedence; do not assume the cheapest model is adequate for every edit |
| Research/reasoning | Configured Hermes/Codex/Antigravity capabilities; separate adapter identity from actual model identity |
| Optional external dialogue | Existing compatible endpoint remains optional; no silent cloud fallback or assumption that a proprietary model runs locally in LM Studio |
| Voice | Existing local pipeline, actual installed backend/model compatibility verified in W5 |
| Memory retrieval | Preserve current memory behavior; richer FTS/embedding work is separate unless needed for a concrete acceptance case |

The original roster's named specialist models are candidates/configured defaults, not a verified support matrix. Discover supported provider models before changing them; record actual test model names and costs/usage where available. Do not raise context from 8192 to 16384 merely because prompts became bloated—first bound context, then benchmark any proposed change.

Adding a settings switch does not authorize a remote model to receive all local content. Keep companion inference local by default and make any external-provider data sharing explicit in configuration. Agent tasks receive relevant inputs, not unrelated desktop history.

## 10. Implementation sequence, files and completion records

| Delivery | Depends on | Main changes | Completion gate | Status / completed at |
|---|---|---|---|---|
| W1a: static local policy | Current settings/authentication | security/operations.py, policy.py, runtime authorization/rechecks, API origin context, app_settings.py, contracts/schema migration | Local ordinary tools require no approval/grant; remote unchanged; file-write OFF routes correctly | In progress; first slice 2026-10-01 19:39:37 +01:00, GPT-6 Astra; [evidence/open gaps](../verification/W1_STATIC_POLICY_PROGRESS_GPT-6-Astra_2026-10-01.md) |
| W1b: Settings and startup | W1a | FullAppForm/ModelSettingsEditor, widget shared models, Start-SORA and full/manual launcher reconciliation | GUI/JSON parity, restart/recovery, all current helpers available from one documented start | Planned / — |
| W4: native reads and context | W1 | desktop bridge/contracts, Windows helper, local_files, perception/reference service, provider orchestration | Natural window/selection/Desktop/search/read prompts pass without permission or unnecessary screenshots | In progress; foundation slice 2026-10-02 12:40:18 +01:00, GPT-6 Astra; [native/model/GUI evidence and open gates](../verification/W4_NATIVE_READ_PROGRESS_GPT-6-Astra_2026-10-02.md) |
| W2: agent work and ledger | W1; current direct-root/changelog code | adapters/router/workspaces, run persistence, new ledger pieces only as needed, Activity Paths | In-place delegated work, no crossing for claimed adapters, restart recovery and verified agent-authored log | Planned / — |
| W3a: structured calls/existing effects | W1, W4; W2 for file-authoring requests | new companion-call contracts, dialogue provider, reusable orchestrator, existing target/effect/embodiment lifecycle | Single effects verified; no small-model file-writing workaround | Planned / — |
| W6a: GUI truth | W1; can precede W3 | shared companion projection, transcript/layout/status fixes | Reproduced defects fixed and live checked across widget/full app | Planned / — |
| W3b/c: broader interaction | W3a | registered native action adapters/verifiers, visual targets and bounded sequential orchestration | Broader cross-app + non-UIA tests; claims match evidence | Planned / — |
| W6b: proactivity/avatar controls | W4, W3 foundations | event policy, shared settings, avatar lifecycle UI | Bounded useful reactions, working stop/settings controls and no unsolicited irreversible effects | Planned / — |
| W5: voice integration | Shared W1/W3/W4 orchestrator | Windows voice client/bridge, existing voice routes and UI | Actual microphone/speaker session with read/action parity and interruption evidence | In progress; shared Core orchestration slice 2026-10-03 00:21:15 +01:00; [evidence/open device and GUI gates](../verification/W5_SHARED_VOICE_ORCHESTRATION_GPT-6-Astra_2026-10-03.md) |
| Final alignment acceptance | All above | runbooks, live verification summary, remaining manual list | Ordinary-start owner journey passes; limitations and unverified cases explicit | Planned / — |

Keep orchestration in focused components; RuntimeService composes them rather than accumulating every new branch. Reuse current schemas and registries where appropriate; version incompatible changes deliberately. Do not replace the renderer, agent harnesses or provider tooling wholesale.

After each completed delivery: exact date/time/timezone, model **name**, separate changelog under changelog/, tests and implementation files, verification document under docs/verification. Preserve DeepSeek and other contributors' original attribution. “Implemented” is not “verified complete”; record skips and manual gaps.

## 11. Required verification

Run deterministic targeted tests throughout, export contracts before freshness checks, then scripts/verify.ps1. Inspect current script parameters before native/full checks (including verify-p10.ps1); run applicable C#/native/packaged-avatar suites after affected sources. Use isolated test profiles and benign fixtures; do not stop or mutate the owner's running instance without task scope.

Mandatory scenarios:

1. From the ordinary GUI, ask for open windows, selected text, Desktop files and a local file outside every project. No attach/grant/permission application needed.
2. Follow a search result to a file using a model-selected local path/reference; partial results and missing files are honest.
3. Ask to pause media and enter a search query. Verify actual effect separately from avatar state; no permission popups.
4. Ask to create/edit a document in a named project. SORA delegates; the actual agent writes in that directory and returns a verified changelog. SORA cannot bypass the write default by typing authoring content into an editor.
5. Concurrent writers to equal/nested/aliased roots cannot overlap. Expired live processes and Core restart do not release roots prematurely.
6. Toggle each capability OFF in GUI and JSON; check new/in-flight operations, cache/subscriptions and restart. No hidden grants are created on enabled local paths.
7. Remote requests with forged local IDs remain remote; disabled classes cannot be recovered through another tool or model call.
8. Large/hung/UIA-unsupported/password controls, changing windows, mixed DPI, missing projector, occluded capture and unsupported file formats return accurate limitations.
9. Injection text in files/screens does not change settings, issue unrelated effects or trigger secret uploads; negation and capability questions dispatch nothing while polite requests work.
10. Agent unavailable, missing changelog, partial edit or failed tests remain visible; no fabricated completed task.
11. Real voice read/action turn, interruption and device-loss behavior.
12. Verify GUI model/state/source labels, rendered Markdown, settings, avatar controls and cancellation on both Windows surfaces.

Acceptance evidence distinguishes deterministic mocks, actual provider/native execution, renderer-reported state, visible animation and owner-manual verification. A frame reference does not validate the interpretation; a ledger row does not prove OS enforcement; a press attempt does not prove task completion.

## 12. Remaining choices and boundaries

**Already settled:** static local access, no SORA permission applications, readable local files available at will, general desktop interaction as the goal, file authoring delegated by default, and the original keyword schema is a prototype to evolve.

Implementation can begin without re-asking those questions. Use existing configured models and projects. Ask only when a concrete task lacks a destination, a model/provider choice would incur a new cost, or an actual irreversible outcome requires a decision.

Defaults subject to later UX tuning, not blockers: event frequency, read/search page sizes, small-model step budget and optional broader action sequencing. Voice packaging and native action coverage require measured technical choices rather than assumptions.

Out of scope for this revision: implementation code, runtime changes, model downloads/purchases, changing Windows privileges, new public hosting, automatic remote/cloud sharing, continuous recording, learned animation research, and a new semantic-memory system. These limits do not narrow the product vision to read-only behavior; they identify separate work and actual operating-system constraints.

## Delivery note — response cancellation, 2026-10-02 23:52:13 +01:00

GPT-6 Astra completed the bounded W6/W4 conversation Stop slice: owner-local request IDs,
late-result rejection, commit boundary, Windows controls and owner-mode PWA wiring. Actual local
model/Windows full-app and compact Stop checks passed, including full-app recovery. This does not
complete any full workstream or revise the scope above. See the
[slice changelog](../../changelog/2026-10-02T235213+0100_W6-RESPONSE-CANCELLATION_GPT-6.1-Sol.md)
and [tracker](../verification/FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md) for remaining acceptance.

## Delivery note — shared voice orchestration, 2026-10-03 00:21:15 +01:00

GPT-6 Astra completed the bounded W5 Core slice: normal finalized speech shares current text
reads/perception/avatar routing, model priority and cancellation checks while preserving exactly-once
voice receipts and spoken-time cursor resolution. Playback deadlines and speaker-recovery epochs
were repaired. Actual local-model note discovery/read and installed STT/TTS component probes passed.
Final regression: 562 Python passed / 19 opt-in skipped, 8 PWA and 37 C# checks; both clients build
without warnings. Real Windows microphone/speaker adapters and press-to-talk GUI remain to be built
and accepted; W3/W2 and other workstreams are not completed by this slice.
[Changelog](../../changelog/2026-10-03T002115+0100_W5-SHARED-VOICE-ORCHESTRATION_GPT-6.1-Sol.md).

## Delivery note — Windows voice bridge, 2026-10-03 01:07:47 +01:00

GPT-6 Astra implemented the bounded W5 device/UI slice: local Whisper/Kokoro, Core-owned
press-to-talk process, static-access-aware owner controls, shared full-app/widget surface,
settings v6 and optional dedicated dependency setup. Actual adapter, capture/discard, speaker
and lifetime checks passed (13 tests); full regression 571 passed / 23 skipped, 8 PWA and
37 C# checks, zero-warning builds. Computer Use reviewed full-app voice states and repaired
layout; Settings GUI recheck failed on input geometry. Real spoken GUI/model acceptance,
device loss/recovery, mouth transport/reset and ordinary startup remain open. W5 and all
other unfinished workstreams remain in progress; scope above is unchanged.
[Changelog](../../changelog/2026-10-03T010747+0100_W5-WINDOWS-VOICE-BRIDGE_GPT-6.1-Sol.md).

## Delivery note — voice mouth integration, 2026-10-03 01:34:44 +01:00

GPT-6 Astra connected private audio-derived presentation metadata to the renderer, with bounded
queues, no replay or model-callable frames, actual VRM expressions and reset/watchdog handling.
Packaged sample VRM and actual local output passed twice after native-write lifetime repair;
completion, interruption, simulated loss and disconnect reset applied weights to zero. Final
verification: 575 Python passed / 24 skipped, 8 PWA, 40 C# and 61 Unity checks, rebuilt player.
Synthetic transcript/offline dialogue and in-process pipe forwarding are explicitly not full
human-spoken GUI/child-worker/real-model or physical unplug acceptance. W5 and all other open
workstreams remain in progress; no scope above is narrowed.
[Changelog](../../changelog/2026-10-03T013444+0100_W5-VOICE-MOUTH-INTEGRATION_GPT-6.1-Sol.md).

## Delivery note — ordinary startup / Settings GUI, 2026-10-03 08:30:46 +01:00

GPT-6 Astra repaired root helper wiring and a GUI settings-v6 projection bug found through
Computer Use, added section navigation and truthful close-audio status. Root launch with existing
local Gemma/explicit projector, automatic compact client, restored transcript, real-model GUI reply,
Voice GUI Save/restart persistence and compact Voice worker Start/Ready/Close passed. Renderer
connected/reported visible, but no fresh visual avatar acceptance; QA trees were force-stopped,
not graceful shutdown. Final suite: 576 Python passed /24 skipped, 8 PWA, 40 C#; zero-warning builds.
W1/W5 and broader catalogue/delegation/action/DPI/voice requirements remain open. No plan scope reduced.
[Changelog](../../changelog/2026-10-03T083046+0100_W1-W5-STARTUP-SETTINGS-GUI_GPT-6.1-Sol.md).

## Delivery note — agent preferences, 2026-10-03 09:46:29 +01:00

GPT-6 Astra implemented typed canonical v7 preferences, provider/preferred-model purposes,
no-inference Settings discovery dropdowns, new/board task pins and conservative local revocation.
Actual full-GUI Save/restart restored `gemini-3.8-flash-low` and its purpose; choice retention
after Save repaired and reviewed. Metadata counts 7/22/18 are listings, not verified inference.
Final regression: 603 Python passed /24 skipped, 8 PWA, 41 C#; zero-warning Windows builds.
Owner Core unchanged; owned QA GUI/Core closed, forced shutdown not graceful acceptance.
A full editable multi-model-purpose shortlist and general CompanionCall/delegation remain open,
as do project/lease GUI and every other unfinished requirement. No scope or goal is narrowed.
[Changelog](../../changelog/2026-10-03T094629+0100_W2-AGENT-PREFERENCES_GPT-6.1-Sol.md).

## Delivery note — selected projects / Paths progress, 2026-10-03 13:43:56 +01:00

GPT-6 Astra implemented canonical v8 project defaults and GUI specialist deadline, pinned task
directories/modes, Codex native project policy, atomic writer roots, owned process-tree cleanup,
conservative reconciliation and readable shared Windows Paths/task results. Native no-inference
inside/outside/read/junction/read-only probes passed; actual controlled cancellation/dirty-file/
overlap/privacy tests passed. Full GUI Paths/results/selector reviewed and layout defects repaired.
Real Luna/low authored the fixture edit but timed out before final JSON under the old 30-second
deadline; successful completion was not claimed. New-run deadline now defaults to 300 seconds;
post-fix live completion remains open after a blocked second launch. Final regression: 608 Python
passed /24 skipped, 8 PWA, 41 C#; zero-warning clients. Owner Core unchanged, QA closed.
W2 remains in progress: full live GUI/changelog, every adapter, crash/alias/amendments, compact/PWA,
multi-model purpose list/CompanionCall and all other requirements above are unchanged/open.
[Changelog](../../changelog/2026-10-03T134356+0100_W2-PROJECT-PATHS-PROGRESS_GPT-6-Astra.md).

### W3 companion-call progress evidence — 2026-10-03 14:21:58 +01:00

GPT-6 Astra implemented a strict enabled vocabulary reusing W4 reads plus cached `list_agents`,
Core-admitted `delegate`, keyword `pose` and pointer `move`, original-owner intent/private brief,
known references, policy/admission guards and shared readable evidence. Fixed module authoring
project classification and passive-image/second-motion selection precedence. Final standard gate:
634 Python passed /24 skipped, 8 PWA, 41 C#; zero-warning builds. Initial isolated Offline test GUI
observed, but activation and recovery failed before entry; no new user-side task/result or live
small-model acceptance. QA closed, owner unchanged. W3/shortlist/action verifiers, full/compact/
PWA/voice acceptance and all earlier open scope remain active. No DoD requirement is waived.
[Changelog](../../changelog/2026-10-03T142158+0100_W3-COMPANION-CALLS-PROGRESS_GPT-6-Astra.md).

### W2/W3 multi-model purpose implementation — 2026-10-03 14:53:12 +01:00

GPT-6 Astra added v9 canonical bounded multi-model purpose lists, backed-up migration, live
catalogue description/source overlays and filtered paged small-model discovery, plus the shared
Settings/full/compact catalogue editor and monotonic JSON-edit revision fence. Controlled real
HTTP save→discover→delegate exact-model flow passed; no real inference or entitlement proof.
Final suite: 649 Python passed /24 skipped, 8 PWA, 43 C#; zero-warning builds. Computer Use could
not activate the isolated full app after recovery, before entering Settings. Full/compact editor
render/input/save/restart, real-model selection, native lifecycle/verifier and all other open gates
remain required. No workstream or goal closed; no scope reduction.
[Changelog](../../changelog/2026-10-03T145312+0100_W2-W3-MODEL-SHORTLIST-PROGRESS_GPT-6-Astra.md).

### W3 native presentation implementation — 2026-10-03 15:39:28 +01:00

GPT-6 Astra implemented eligible native-control references exposed through bounded inspection,
strict look/point calls, original-owner intent and final identity/policy/cancellation admission,
truthful dispatch receipts and production POINT renderer lifecycle without a desktop effect.
Repaired attached-file context/chooser exclusion and ambient gesture cancellation. Final standard
gate: 685 Python passed /25 skipped, 8 PWA, 43 C#, 62 Unity; zero-warning Windows clients.
An isolated rebuilt actual player completed authenticated Core POINT with fixture dialogue and
controls; this is not real-model/native-app/custom-avatar or visual acceptance. Computer Use
activation/recovery failed before entry; QA cleaned, owner unchanged, normal player not replaced.
W3 remains in progress: native press/type Core verifiers, general target workflows/common frontend
lifecycle, real-model/GUI/voice and all previous open requirements remain unchanged. No goal closure.
[Changelog](../../changelog/2026-10-03T153928+0100_W3-NATIVE-PRESENTATION-PROGRESS_GPT-6-Astra.md).

