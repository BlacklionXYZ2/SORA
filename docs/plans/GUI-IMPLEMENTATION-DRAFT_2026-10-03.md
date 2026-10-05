# SORA GUI implementation draft

Date: 3 October 2026  
Author: GPT-6 (Codex)  
Status: **Draft for owner review. Planning only; no GUI or Core implementation is delivered by this document.**

## 1. Goal and authority

Deliver a working Windows desktop companion interface following **SORA GUI Design & Interface Architecture — v0.1** and its four supplied concept images: Chat, Automations, Memory and Settings. SORA's avatar is the ordinary presence; independently summonable windows provide conversation and system access.

The attached design is the approved product/visual baseline. Dimensions, tokens, shortcuts, implementation choices and delivery stages below are **proposed defaults**, filling its open questions. They can be adjusted after a connected prototype. The concepts establish composition and identity; their example content, metrics and model capabilities are not runtime specifications.

Preserve [SORA_OVERVIEW.md](../../SORA_OVERVIEW.md), historical phase IDs and evidence in [SORA_IMPLEMENTATION_PLAN.md](../../SORA_IMPLEMENTATION_PLAN.md). This draft does not close or reopen any existing phase. For local access, preserve the owner's static Settings policy in [Vision alignment](VISION-ALIGNMENT_2026-10-01.md): ordinary enabled companion operations do not require recurring approval prompts. User configuration edits remain deliberate user actions.

**Completion means connected functionality from the ordinary launcher, with live acceptance evidence.** A screenshot, fixture, compiled window or configured provider alone cannot establish completion.

## 2. Starting point and scope

Source inspected for this draft:

- `clients/desktop_app`: .NET 10 Windows Forms application, `Program.cs`, `FullAppForm.cs`, `ModelSettingsEditor.cs` and existing board surface.
- `clients/desktop_widget`: shared API client/synchronization models, voice, model-purpose, catalogue, project-path and task-evidence forms.
- `src/sora/runtime/service.py`, memory contracts/capture code and API routing: existing dialogue, canonical memory and task services; presentation adapters should reuse these.
- [Settings guide](../runbooks/SORA_SETTINGS.md): versioned canonical settings, access/perception controls, model reload, voice and effect tiers. It explicitly excludes arbitrary extra runtime arguments in the current release.
- Ordinary and full launch scripts, and existing repository verification script.

This was bounded source/document inspection, not a live runtime audit. Full Memory browsing/graph and a persistent automation scheduler were **not established** by that inspection. Stage GUI-0 must determine their exact availability before assigning implementation work. Historical acceptance claims remain historical.

In scope: window lifecycle, shared controls, connected Chat/Settings/Memory/Automations, preservation of task/artifact/integration access, deterministic panel presentation, accessibility, desktop behavior and normal-launch acceptance. Add only the Core contracts/services necessary for these workflows.

Outside this GUI delivery: learned motion, custom brain/router training, LoRA utility, replacing dialogue/agent orchestration, broad new desktop-action support, a new memory intelligence system, remote/mobile redesign and an unrestricted runtime argument editor. GUI delivery does not depend on a new System-1 model or proving the 2B architecture proposal.

## 3. Proposed implementation architecture

### Native Windows shell first

Keep the existing .NET 10/WinForms host for the first working delivery. Extract reusable presenters/services and split the monolithic form into separate panels. Use native resizable top-level windows, normal activation/minimize semantics and OS shadows/corners where supported. Start with a sufficiently opaque dark theme; native backdrop/blur is optional polish with an opaque fallback. Do not apply opacity to the entire window, which would also fade text and controls.

Before committing to advanced custom chrome or the graph renderer, build a small connected shell and graph spike. If WinForms cannot meet the required accessibility, rendering or DPI behavior, record a concrete WPF/other-native migration decision at GUI-0. A framework rewrite is not the default prerequisite. A web/Electron shell and Unity-rendered form controls are not required by this plan.

### Responsibilities

| Component | Owns |
|---|---|
| Desktop host / application context | Process lifetime, tray, single-instance activation, shortcuts, panel registry, window preferences |
| Shared client services | Authenticated Core transport, connection state, cancellation, cached projections, revisions and event/poll reconciliation |
| Panel presenters | View state and unsaved drafts; mapping canonical projections to controls |
| Core | Conversation, memories, tasks, automations, effective settings, policy and outcomes |
| Presentation coordinator | Typed open/select/highlight requests, UI target resolution, acknowledgements and cancellation |
| Unity avatar | Existing deterministic poses/gestures; visual presentation only |

Closing the last panel leaves the desktop host alive. Use an application context rather than tying process lifetime to Chat or Settings. Repeated launch activates the existing host instead of creating duplicate windows, voice workers or subscriptions. Preserve the ordinary launcher/Core lifecycle rather than adding a competing startup path.

Panels never open SQLite directly or contact reasoning providers directly. Reuse the existing authenticated client initially; extract its shared transport/models without copying independent implementations into each window. Do not silently run both the legacy widget and replacement Chat as competing default text surfaces.

UI-only preferences (bounds, last selected view, theme, compact mode) may live in one versioned desktop preference store. Effective model, voice, access and automation settings remain Core-owned. Never put credentials in the preference store.

## 4. Window and navigation contract

Default boot: avatar plus tray presence, no open application window. First use may show a dismissible orientation surface explaining how to summon Chat and Settings. If avatar startup fails, expose a clear tray status and recovery access; a failed model must not prevent Settings opening.

Tray menu: Chat, Memory, Automations, Settings, Activity, hide/show avatar, start/stop voice, connection status, and Quit SORA. Quit follows the existing managed lifecycle and handles active work explicitly; it must not silently leave untracked workers. Closing panels does not cancel tasks or stop voice. Microphone activity remains visible on the avatar/tray when Chat is closed.

Proposed configurable global shortcut: `Ctrl+Alt+Space` summons Chat. Detect registration conflicts and offer another binding; never claim a shortcut works if Windows rejected it. A summonable command menu lists all panels with plain labels. Direct avatar interaction opens that menu. Asking SORA uses the same panel registry, but essential controls work without a model.

One instance per first-class panel. Reopening an existing panel brings it forward for a user request; it preserves its draft and selection. SORA-originated presentation opens without stealing focus by default. She may explicitly focus in response to a user request. A dismissed suggestion does not reopen for the same request. Minimized user windows stay minimized unless the user asks to show them.

User-opened panels restore valid placement; first open uses a sensible working-area position. SORA-opened panels prefer space beside the avatar, then the least obstructive fitting position. User placement wins over automatic rearrangement. Move windows together only through an explicit arrange command. Inspector details are docked inside Memory by default; detached inspectors are later optional polish.

Store bounds with monitor identity and DPI context. Restore by converting/clamping to the current work area; monitor removal returns inaccessible windows to an available display. Never cover taskbars or leave the title bar unreachable. Keep windows normally layered, with an optional user-controlled pin; SORA cannot make them perpetually topmost. Suppress unsolicited panels in fullscreen/presentation mode, retaining pending activity for later.

Keyboard: Enter sends, Shift+Enter inserts a newline; IME composition never submits. Tab navigation and visible focus work throughout. Escape closes a transient menu/highlight before affecting a panel; it does not discard drafts or cancel tasks. Native close/minimize remain familiar. Unsaved persistent edits receive Save / Discard / Keep editing on close; composer drafts are retained without a dialog.

## 5. Initial visual and layout specification

All dimensions are logical pixels at 100% scaling, proposed for the first prototype. Layout must respond to usable work area instead of enforcing a minimum larger than the display.

| Token | Proposed value |
|---|---|
| Panel base / elevated surface | `#111B2B` / `#1A283B` |
| Primary / secondary text | `#EDF3FB` / `#AAB9CC` |
| Accent / selection | `#48C7F0` / `#244D70` |
| Success / warning / error | `#35C88A` / `#E7B653` / `#EF7B83`, always paired with text/icon |
| Spacing scale | 4, 8, 12, 16, 24, 32 |
| Panel radius / control radius | 14 / 8 |
| Typography | Segoe UI; body 14, secondary 12, section 16, title 20; follow OS text scaling |
| Interactive height | 36 minimum; icon hit area at least 32 × 32 |
| Panel appearance | 140–180 ms subtle fade; at most 8 px translation; no compulsory scale animation |
| Highlight | 500–800 ms pulse, at most two cycles; static equivalent with reduced motion |

Treat colors as candidates until measured: normal text contrast at least 4.5:1; essential control boundaries/focus indicators at least 3:1. Never encode status only in color. Hover glow is restrained; body text and large content regions remain steady. Honor high contrast and reduced motion; provide opaque mode. Native/custom chrome must preserve resize affordances, accessible names and Windows keyboard/window controls.

| Panel | Initial / minimum size | Responsive behavior |
|---|---|---|
| Chat compact | 460 × 560 / 360 × 400 | One-column transcript and composer |
| Chat expanded | 820 × 700 / 600 × 480 | Optional history rail; detail drawer replaces inline crowding |
| Memory | 980 × 680 / 640 × 480 | Inspector docks right when space allows; otherwise replaces main view with Back |
| Automations | 980 × 680 / 640 × 480 | List/detail split; narrower mode navigates list → detail |
| Settings | 980 × 720 / 640 × 480 | Category rail; on narrow displays use category selector and one content column |

Do not shrink labels to fit. Wrap, scroll the relevant content region, collapse secondary sections and keep primary actions reachable. Test bright/dark wallpapers and busy application backgrounds, not just the supplied scene.

## 6. Chat and activity

Compact mode contains transcript, composer, send/stop, microphone and an overflow menu. Expanded mode adds history, attachments and activity details. Both project the same canonical conversation; changing mode never resends, loses draft text or starts another session.

Conversation states: connecting, ready, sending, awaiting response, receiving (if the transport actually streams), cancelled, failed, disconnected. Show receipt/pending state per message; do not imply streaming if the backend returns whole replies. Preserve scroll position unless the user is already at the bottom; show a New messages control otherwise. Retain and clearly mark the last known transcript during reconnection.

Activity chips represent actual Core events and link to their recorded results. Examples: memory retrieved, panel opened, specialist working, artifact created, action failed. Distinguish requested, running, succeeded, failed and unknown. A successful gesture is never proof that an action completed. Unsupported chip types still expose a readable details view.

Stop response uses existing response cancellation/output semantics; it does not automatically cancel an independent agent. Task details offer explicit Cancel task and steering controls. Background work does not disable ordinary conversation. Attachment handling uses existing adapters; show unsupported formats/errors honestly. Voice Start/Stop, listening, processing, speaking and device-error states reuse existing voice services. Closing Chat must not strand an active microphone without indication.

Preserve existing Activity, Content, board, project-path, agent-catalogue and task-evidence functionality. Initially expose these existing surfaces through the command menu, expanded Chat activity drawer and Settings → Tools. This avoids losing functionality while keeping the approved four panels primary. Do not force agent execution history into scheduled Automations: a task run and an automation definition are different records. Deliver artifact links and task cancellation in the first connected Chat milestone.

## 7. Settings

Categories: General, Appearance, Models, Audio, Vision, Memory, Tools, Automation, Performance, Advanced. Empty/unimplemented categories explain their status; no decorative switches. Put companion access under Tools, perception under Vision, and avatar/distraction preferences under Appearance, with cross-links where helpful.

Models distinguishes direct conversation, configured specialist agents and any supported purpose-specific models. A single generic Loaded indicator must not imply all of them are ready. Separate configured, available, loading, active and failed states. Capabilities come from actual provider/configuration support and validation, not the illustrative Llama card.

Disclosure:

1. Model/provider identity, operational status, Change model, basic resource information when measured.
2. Runtime, configured versus active context, projector and supported cache controls.
3. Advanced typed settings and read-only sanitized launch arguments. Preserve current prohibition on arbitrary arguments; adding raw editable controls is a separate runtime change.

Reuse canonical revision checks, validation, migration and last-known-good recovery. Show unsaved draft, saved configuration and effective configuration separately. Every field has an effect label: Immediate, Model reload or Next boot. Save does not imply Reload. Disable Reload while unsaved edits would make its meaning ambiguous. On stale revisions, preserve the draft and offer reload/reconciliation instead of overwriting newer settings. Validate before stopping a working model; failed reload exposes recovery/retry without fabricating readiness.

Do not invent VRAM, confidence, cache usage or throughput values. Display Not available when no supported telemetry exists. Avoid placing passwords/tokens in saved-settings or argument displays.

## 8. Memory

First usable delivery is Overview + Search + inspector over canonical records. Overview shows recent memories and available source/type filters; Search is paginated with debounce, cancellation and no-results states. Select a result to inspect content, creation/update time if available, source/provenance, sensitivity and actual supported metadata. Technical IDs are available in details/copy, not required for normal selection.

Audit the existing schema before exposing importance/relevance. Relevance is query-specific, not an intrinsic permanent score. If the backend cannot supply a metric, omit it. The panel must not expose private reasoning/capture fields as memory content or activity evidence.

Graph follows after browsing works. Query a bounded neighborhood around a selected record, initially no more than 75 nodes; expand on demand. Pan, zoom, search, select and centre have keyboard/list equivalents. Keep layout stable while reading. Render real supported relationships and distinguish explicit links from inferred associations. Do not manufacture links from co-occurrence or similarity merely to populate the art. Without relationship data, show the available records and an honest empty graph state; adding persisted relationship semantics is a narrow prerequisite, not a wholesale memory rebuild.

`present_memory(id)` opens Memory, resolves the record, selects it and highlights it. Use Graph only when a useful neighborhood exists; otherwise present the inspector. Pulses map to actual retrieval events and matching visible IDs; failed resolution reports unavailable/deleted instead of highlighting another node.

Memory is read-only in the first milestone. Any later edit/forget flow requires an existing or newly specified canonical mutation contract, preview and explicit user action. Define retention, backing-capture behavior and restoration honestly before offering Undo; hiding a row is not forgetting a memory.

## 9. Automations

Provide All / Active / Paused filters; list name, trigger, last outcome and next scheduled occurrence. Detail contains Overview, Edit and Logs. Overview separates schedule, behavior, configured tools and execution history. Logs link to the real run, result and error; do not substitute generated success summaries for evidence.

GUI-0 must establish whether a persistent scheduler exists. Reuse it if suitable. Otherwise add a minimal Core-owned automation service as a GUI dependency: stable IDs, versioned definitions, persistence, validated triggers, scheduling, pause/resume, run history and dispatch to the existing task service. A functional-looking panel with no scheduler does not count as a delivered Automations panel.

First scheduler scope: one-off and daily/weekly local-time schedules, explicit timezone, owner-edited behavior and registered supported capability references. Support New, Save, Pause/Resume and Run now. Defer arbitrary event triggers, chained workflows and raw cron editing. Scheduler correctness includes restart reconciliation, next occurrence, daylight-saving policy, no overlapping runs by default and duplicate occurrence protection. Use occurrence IDs; do not claim exactly-once external effects after an ambiguous crash.

Proposed scheduling rules: display timezone and next actual date/time; skip a nonexistent spring-forward time with a visible history reason; run once at the first matching autumn repeated time. Missed executions default to skip, with an explicit bounded run-once catch-up option. No burst replay of old schedules. Resume calculates the next future occurrence. Run now is a separate manual occurrence and does not move the scheduled next run.

For the first version, retries are manual; unsupported/background failures remain visible. Pause stops future scheduling, while a running job is cancelled separately. Automation edits use revisions and affect future runs; record the version used by each run. If a needed capability is disabled/unavailable, show the actual blocked/failure reason. SORA may present/explain an automation but cannot silently enable it or alter its schedule.

## 10. SORA presenting her own panels

Use a small typed UI vocabulary: `present_panel`, `present_memory`, `present_automation`, `highlight_target`, `clear_annotation`. Expose only implemented semantic targets. Resolve target IDs inside the desktop host; never ask the model for pixel coordinates, window handles or raw UI selectors.

Each command carries request identity, panel/record identity, origin, expiry and optional presentation mode. Return an acknowledgement: opened, already visible, selected, target unavailable, deferred or rejected. Emit Opened Memory panel only after acknowledgement. Repeated delivery is idempotent. A user selection change or stale record cancels an obsolete highlight.

Distinguish user-solicited navigation from ambient suggestions. Automatic focus/close must not interrupt typing or discard drafts. For the first version, SORA does not close user-opened panels autonomously. Highlights refer only to her own registered controls/records. General annotations over other applications are deferred.

Notes are temporary presentation overlays, not memory writes: proposed 8-second default lifetime, dismissible and cleared on target disappearance. Anchors follow panel movement/scroll/layout through registered control bounds. Avoid hit-test interception except an explicit dismiss affordance. Full pointing/relationship lines are optional after basic highlighting works, with reduced-motion fallback. Avatar pointing may fail gracefully without blocking panel selection or Core completion.

The first UI state projection needs only visible panel IDs, selected record IDs, interaction/unsaved-draft flags and presentation acknowledgements. Do not require continuous desktop capture or a new router. Add bounded context fields through existing capability/context plumbing only when needed.

## 11. Delivery stages and gates

Implement in small, reviewable increments. Every stage records source changes, fresh validation, remaining gaps and model attribution in a changelog; no historical tests presented as new evidence.

| Stage | Work | Exit evidence |
|---|---|---|
| GUI-0: contract and shell spike | Inventory current endpoints/services; map legacy features; confirm launcher/single-instance lifecycle, Memory/Automation gaps and graph renderer choice; prototype connected native shell | Contract matrix with supported/missing fields; tray can open Settings without a working model; normal-launch and DPI spike results; framework decision |
| GUI-1: host and connected Chat | Window manager, theme primitives, tray/shortcut, compact/expanded Chat, drafts, connection/error states, task/artifact access, existing voice wiring | Close all panels and reopen; no duplicate host/workers; real text turn, failure/retry, stop, independent task cancellation and microphone indication |
| GUI-2: connected Settings | Split existing editor into categories, retain controls/revisions/effect tiers, static access, recovery, model/agent distinctions | Save/persistence, stale edit, restart and actual reload/failure/recovery; no lost supported legacy controls |
| GUI-3: Memory browser and presentation slice | Canonical list/search/inspector; narrow API additions if needed; typed `present_memory` and acknowledged highlight | Real known memory found/selected; unknown ID handled; real activity chip opens correct record; no capture-reasoning disclosure |
| GUI-4: usable Automations | Core scheduler gap resolved; connected list/editor/history, one-off/daily/weekly, pause/resume/run-now | Actual scheduled execution/result; pause, restart, DST/missed-run/duplicate tests and visible failure |
| GUI-5: graph and spatial refinement | Real relationship neighborhoods, stable graph, retrieval pulses, responsive layouts, optional backdrop/gesture/notes | Large dataset remains bounded; edges traceable; input/DPI accessible; stale targets and reduced motion work |
| GUI-6: ordinary-use acceptance | Installer/launcher integration, preference migration, recovery, multi-monitor/fullscreen and performance checks | Fresh normal-launch end-to-end evidence; no reliance on a special QA launcher; documented remaining optional polish |

**First reviewable milestone: GUI-1 + GUI-2.** It establishes the everyday GUI before graph work. **First proof of the distinctive interaction: GUI-3**, conversation → activity chip → actual memory → selected inspector/highlight. **Full baseline functional completion requires GUI-4 and GUI-5**, not only attractive Chat and Settings windows.

Memory/Automation contracts can be developed independently after GUI-0, but shared host/transport/settings changes need coordinated ownership. This document does not require parallel agents.

## 12. Verification and release definition

Use focused C# presenter/window-manager checks and Core/API tests for changed contracts. Meaningful tests cover revisions, duplicate commands, reconnect, scheduler occurrences and cancellation; visual style does not need mirrored implementation tests. Run `scripts/verify.ps1` for integrated milestones and any existing relevant client checks. Export affected generated contracts before their freshness gate. If Unity source changes, run its applicable final-source build/tests; a GUI-only stage does not require rewriting avatar tests.

Use an isolated test Core/profile for destructive/settings/scheduler scenarios, then a separately recorded ordinary-launch acceptance pass. Do not overwrite the owner's active settings or memories to manufacture evidence. Inspect rendered windows with the available computer-use workflow during implementation; label any inaccessible native UI validation as unverified rather than passed.

Required manual matrix:

- 100%, 150%, 200% DPI; mixed-DPI move; small usable work area; monitor disconnect/reconnect; sleep/resume.
- Dark/bright wallpaper, busy background, opaque/high-contrast modes, OS text scaling, keyboard-only use, screen-reader names/focus and reduced motion.
- Core absent/restarting, token refresh, provider unavailable, model reload failure, disconnected caches and cancelled requests.
- User typing while SORA suggests a panel; repeated summon; fullscreen suppression; unsaved settings close; tray Quit with active work.
- Real microphone/speaker start, stop and device-error state; real agent task/results where configured; real memory and scheduled run.

Proposed UI targets: local menu/open feedback within 100 ms; no UI-thread blocking on Core/provider calls; panel skeleton within 250 ms on the owner machine once the host is running. Data/model latency is measured separately. Bound memory graph/list work and connection polling; avoid a per-panel unbounded timer/subscription. Record measured values and hardware before calling performance accepted.

Baseline release requires: all four panels connected; no ordinary persistent app frame; recovery access without the model/avatar; task/artifact/integration access preserved; readable/resizable accessible layouts; canonical state/revision handling; confirmed restart persistence; real run/error evidence; static access policy preserved; no fabricated telemetry/relationships; and a changelog clearly separating completed work from optional/deferred polish.

## 13. Decisions this draft proposes

Proceed with native incremental delivery, four primary windows, a tray/shortcut recovery path, docked Memory inspector, read-only Memory first, restricted initial scheduler triggers, opaque content before blur, and existing voice/model/agent paths. Keep activity/artifacts as secondary reachable surfaces. Prioritize GUI-1/GUI-2 and then the Memory interaction slice; defer learned motion, router training and editable raw runtime arguments.

The owner need not settle every pixel value before work starts. GUI-0 should resolve actual framework/contract gaps; connected prototypes should refine size, spacing and placement. Any scope expansion needed for a missing scheduler or memory relationship service should be described explicitly before it is treated as part of implemented GUI behavior.
