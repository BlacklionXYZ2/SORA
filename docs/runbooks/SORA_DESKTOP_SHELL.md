# Opt-in SORA desktop host and UI preferences

The new desktop host is an opt-in developer/QA entry point during the GUI roadmap. It supports managed Core launch through root `Start-SORA.ps1 -Client Shell` and `scripts/start-full-sora.ps1 -Client Shell`, but is **not the ordinary default or the finished reference-style GUI**. Existing Desktop/Widget/Browser modes remain available; Desktop remains the default.

## Open the host

For an opt-in managed launch, run from the project folder:

```powershell
.\Start-SORA.ps1 -Client Shell
# Or explicitly choose a separate profile and open recovery/settings:
.\Start-SORA.ps1 -Client Shell -StateRoot C:\path\to\profile -ShellPanel settings
# Full-launcher specialist selections are also supported:
.\scripts\start-full-sora.ps1 -Client Shell -CodexModel gpt-5.6-luna -AntigravityEffort medium
```

The first launch is windowless by default, with tray/shortcut access. A repeat launch for the same profile summons the command menu unless a panel is specified. The primary host decides whether to attach to a verified same-profile Core or start one owned Core; secondary hosts do not launch services. Existing model/settings/avatar/workspace/write-repository/timeout selections and native helper wiring are retained through the manual startup script. `-SetupVoice` runs only as part of an actual owned startup, not a secondary summon. `-NoClient` cannot be combined with Shell.

The full-launcher Shell branch delegates before any service/setup work, preserving its Codex/Antigravity model and low/medium/high effort selections, `-NoAntigravitySkipPermissions`, selected paths, timeout, avatar/voice options and explicit/default port distinction. It uses canonical settings/defaults, not the manual launcher's opportunistic legacy llama/external discovery when settings are absent. Core's supported Antigravity efforts do not include `max`; the launcher now rejects it rather than failing later or silently mapping it. Saved canonical agent preferences remain authoritative where applicable; passing a model string does not prove provider availability. Root/manual launch additionally accept explicit specialist overrides without changing their previous default skip-permission behavior.

Without an explicit `-Port`, a validated saved descriptor supplies the profile endpoint. An explicit different port is refused if the saved endpoint is occupied/uncertain; unknown occupied listeners are not bypassed by picking another port. The Shell path does not silently restart an older incompatible running Core. Do not switch the owner profile to this mode until its existing runtime has been stopped normally and the remaining acceptance limits are understood.

For attach-only developer use, build `clients/desktop_shell/desktop_shell.csproj`, then select the exact profile and its compatible loopback Core. This direct command does **not** start services. Replace these example paths with your chosen profile:

```powershell
dotnet build clients/desktop_shell/desktop_shell.csproj
& .\clients\desktop_shell\bin\Debug\net10.0-windows\SoraShell.exe `
  --core-url http://127.0.0.1:8765 `
  --token-file C:\path\to\profile\private\sora-api-token `
  --state-root C:\path\to\profile `
  --show menu
```

Supported entry requests: `none` (windowless boot), `chat`, `voice`, `activity`, `agents`, `paths`, `board`, `content`, `integrations`, `settings`, `appearance`, `menu`, `quit`. Root/full Shell launch also accepts `-ShellPanel voice|activity|agents|paths|board|content|integrations|settings`. A repeat launch forwards to the existing host for that profile and exits; even the command menu belongs to the primary host. It does not start another Core/model/player or another UI connection owner.

`appearance`, the command menu and Settings window work with Core unavailable or no inference/avatar. Online Chat and canonical Settings effects require authenticated matching profile/instance identity. An older running Core without `/api/v1/runtime/identity` fails closed with diagnostics; this host does not silently restart it, adopt an unrelated port or bypass the check. Hosted `settings` now contains the categorized full AppSettings v9 editor; a retained projection/draft remains inspectable offline, but effects are disabled. An initial unavailable Core cannot supply saved values: the panel explains this instead of inventing defaults. The standalone GUI-0 prototype still has its named read-only probe.

## Canonical Settings

Open Settings from tray/menu/Chat or use `-Client Shell -ShellPanel settings`. The ten-category rail groups all84 current editable preferences; **Show advanced controls** reveals less common fields without deleting them. [The field map](../gui/GUI2_SETTINGS_FIELD_MAP_GPT-6.1-Sol_2026-10-04.md) documents categories, kinds and effect tiers. Older v9 projections are categorized without requiring a Core restart.

- **Save settings** validates/persists through Core. Immediate access/perception/agent controls apply on Save; voice changes stop active audio, which must be started again explicitly. Model fields stay pending until **Reload model**; next-start fields do not restart Core automatically.
- **Reload model** uses saved revision only and is disabled with an unsaved/conflicting/unknown-outcome draft. Actual compatibility/runtime support is established by Core's load, not by a file picker or model ID.
- **Refresh from disk** is an explicit live-settings effect, not merely a read. Its confirmation describes possible voice stop/agent revocation. Invalid-file recovery/byte-preserving backup remains Core-owned. A failed/unconfirmed refresh retains the draft.
- **View saved settings** inspects current projected saved values. Badges expose saved/effective values; Models displays actual Core model/runtime/context/cache details and labels missing telemetry. **Advanced** now has read-only launch arrays: Core-captured submitted managed-worker arguments, the next model reload preview (current boot settings) and the next Core start preview (saved boot changes). Previews do not validate files/runtime or load anything; submitted capture is not independent OS attestation. No environment/credentials/logs, guessed VRAM, arbitrary raw-flag editor or executor. Older Cores explicitly report unavailable launch details. [Launch-details verification](../verification/GUI2_LAUNCH_DETAILS_GPT-6.1-Sol_2026-10-04.md).
- Closing Settings hides it and keeps its process-local draft. Conflict/error does not erase edits or automatically retry Save. **Reconcile draft** reads current saved values, shows previous/current/local values for your edited fields and asks whether to retain those edits; untouched fields adopt the latest saved values. This is an explicit reviewed rebase, not Save or an automatic three-way merge. Alternatively, **Discard draft** starts again from saved values. Host Quit asks about a dirty draft and refuses pending operations; accepted shutdown freezes further edits.
- Audio pickers offer current unique input/output device keys; blank means Windows default. Stale/ambiguous inventory is not silently selected, typed values are retained, and this does not itself open a microphone. Appearance remains a separate UI-only store; Memory has a separate browser but no editable v9 preferences, while Automation service/settings remain upcoming.

[GUI-2 verification](../verification/GUI2_SETTINGS_GPT-6.1-Sol_2026-10-04.md) records component/API boundaries. Actual new Settings render/input/hide/restart/DPI/keyboard/device/model-reload acceptance and final reference styling remain open.

## Appearance and panels

Open **Appearance / panels** from the tray or command menu, or use `--show appearance`.

- Dark or Windows system-colour palette; Windows high contrast takes precedence. System colours are not a promise of a custom dark/light OS-theme renderer.
- Panel text size, 85–175%, independent of Windows display DPI.
- Compact Chat, explicit Chat pin, and Chat technical-detail preference. Old widget topmost is not silently applied.
- Chat shortcut: `Ctrl+Alt+Space`, `Ctrl+Alt+S`, or None. Save re-registers it; conflicts are visible and menu access remains available.
- Reduced-motion preference is retained, with an explicit note that the current panels are static. No entrance/graph animation is claimed.
- Save/Cancel, explicit reload, placement-only reset and invalid-file recovery. Unsaved UI edits require a decision before host Quit. Remote IPC Quit rejects unresolved edits instead of popping a timed-out modal.

Closing Chat hides it and retains its process-local draft; it is not Stop response or task cancellation. Compact/expanded changes share the same draft. Drafts/transcripts/tokens are **not written to UI preferences**, so a desktop-host restart does not restore an unsent Chat draft from disk.

## Connected Chat slice

Hosted Chat now uses a shared compact/expanded presenter rather than showing prototype tabs. **More** opens Settings/recovery, reconnect and an optional local-file path entry. **Attach** opens the native multi-file picker (at most three selected files per turn). Chips show filenames; their accessible names/tooltips show full paths. Clicking a chip removes the selection from this turn, **not the file from disk**. Selecting a path does not read or preview its contents; explicit Send passes typed `file_paths` to Core, which applies current static settings and existing file/image handling. A file-read disable is respected without a new permission request.

Draft text and selected files survive compact changes, hide/reopen, errors and Stop. Successful sends clear only the draft revision and selection IDs actually submitted, preserving newly edited text or re-selected files while a response was pending. No send is automatically retried. These selections remain process-local and are not saved to UI preferences.

The transcript is a read-only native text/code projection with speaker labels and Core message timestamps. URLs and HTML are inert readable text, not active web content; unsupported Markdown is not a promise of full browser-style formatting. Unchanged refreshes do not rebuild the document. When reading earlier content, append-only updates retain the scroll position and expose **New messages**; that button explicitly jumps to the latest response. Rebuilds now use measured spans keyed by message IDs; deleted/corrected/ambiguous selections clear rather than select another record. The ID mapping has component tests, but native shifted-history/restyle acceptance and a full paging/history browser remain open.

Enter is intended to send; Shift+Enter adds a line. The presenter rejects IME commit/newline/modifier submission, but physical keyboard/IME acceptance remains open. **Stop** uses the exact in-flight request identity; it does not undo effects already dispatched or cancel an independent task. The API returns whole responses: there is no simulated token stream. Voice and real activity/evidence chips are later GUI-1 work, not placeholder controls. [Initial Chat verification](../verification/GUI1_CHAT_GPT-6.1-Sol_2026-10-04.md) separates native fixture checks from component and real-provider evidence.

## Activity / task evidence

Open **Activity / task evidence** from Chat More, tray or command menu; direct attach-only `--show activity` and root/full-launcher `-Client Shell -ShellPanel activity` use the same primary host. This initial GUI-1c slice shows the current bounded task list from the shared Core session, not another panel poller. Select an exact task and choose **Open / refresh evidence** for its original request, separately labelled SORA brief, requested model/project/base ref, provider result/artifacts and coverage. Paths/URLs are inert text; a result reference is not assumed to be a local file. Missing data is labelled, not fabricated.

**Cancel task** and **Send instruction** are independent of Chat Stop. They ask for an explicit task-target decision, re-read the captured ID/current state, reject terminal/unknown or changed Core targets, and never replay automatically. Acknowledgement is not proof of final task completion or Undo. These controls require matching connected Core, but not a loaded dialogue model. Offline cached list/evidence is labelled stale and effects disabled. Changing selection while a read is pending cannot show the old task's reply under the new selection. Closing Activity hides it and retains the process-local instruction; an in-flight control must settle before host Quit.

Activity placement is another recognized key in the UI-only version1 store; existing stores remain valid. Older Shell binaries that do not recognize the Activity key fail read-only and preserve it rather than reset it. Agent/delegation selection, board/content/integration surfaces, full run history and real public-event chips still need migration. [Chat/Activity verification](../verification/GUI1_CHAT_ACTIVITY_GPT-6.1-Sol_2026-10-04.md) records component task controls, fixture HTTP file context and actual offline Activity rendering—not online user-side task-control acceptance.

Use the tray or command menu's **Quit SORA (owned services only)** for managed Quit. A local confirmation explains Core/voice/avatar/task consequences; accepted shutdown is not task cancellation. The host waits for its owned launcher and listener absence. If cleanup is not confirmed, it remains available with diagnostics rather than force-killing or starting a replacement. Quit of an attached external Core closes only the host and leaves Core/tasks running. `--show quit` over IPC is refused while the primary has an owned launch or pending managed initialization; it must not silently trigger managed shutdown.

## Agents / delegate task and Project paths / writers

Both retained surfaces are available from tray, command menu and Chat More. For opt-in managed launch/summon:

```powershell
.\Start-SORA.ps1 -Client Shell -ShellPanel agents
.\Start-SORA.ps1 -Client Shell -ShellPanel paths
```

Agents has a separate process-local task draft; it does not submit your Chat draft or change the local dialogue model. **Read cached list** reads configured metadata without discovery. **Refresh models** explicitly performs the existing metadata probes; its notice explains the empty Hermes ACP session. Neither operation starts an agent task, and listed IDs do not prove model access.

Choose an exact provider/model/effort and actual project/mode where supported, then deliberately **Start specialist task**. Saved purposes/capabilities/base ref remain inspectable; task deadline is Core-configured and this selector offers no per-task base-ref/deadline override. **Edit model purposes** reuses the existing revision-checked canonical editor, not the read-only hosted Settings projection. Conflicts/errors preserve its draft.

An unconfirmed submission freezes its text/selections and retains the same key for **Retry exact submission**; retries are explicit, not automatic. Inspect Activity first if uncertain. Changed Core instances cannot receive a retry of that old request. An acknowledged draft cannot start again; **New task** creates a separate request. A known invalid-input rejection before admission permits correction. The receipt reports task/requested selection/admission state, never independent execution success. Unknown submissions cannot be silently changed into a different model/project request.

Paths shows canonical reservations and recent path evidence with source/coverage labels. **Refresh** reads evidence. **Recheck stopped writers** explicitly invokes existing Core reconciliation after a consequence decision; it is not force unlock, task cancellation or a complete filesystem audit. Uncertainty retains reservations.

Both panels hide on close and retain process-local state. Offline/changed-Core data is marked stale; effects require the matching Core, not a loaded dialogue model. No new panel poller, connection, agent or speech worker is created. Pending catalogue/purpose/path operations must settle before host Quit. UI-only version1 recognizes `agents` and `paths` placements; older binaries preserve unfamiliar keys read-only.

[Verification and remaining gates](../verification/GUI1_AGENTS_PATHS_GPT-6.1-Sol_2026-10-04.md) distinguish component guards, actual cached/empty/offline rendering and unverified native submission/purpose/recheck/hide-retention/provider acceptance. The later Board/Content/integration implementation is described below; full run history/public chips and native acceptance remain open. Compatibility clients remain available. Nothing in these slices completes GUI-1 or GUI-2.

## Note board, Content and Integrations

Open these retained surfaces from Chat More, the tray or command menu. Direct attach-only `--show board|content|integrations` and root/full `-Client Shell -ShellPanel board|content|integrations` use the same host. This slice is built/component-tested, **not yet native GUI accepted**; see the [verification report](../verification/GUI1_BOARD_CONTENT_GPT-6.1-Sol_2026-10-04.md).

The compact note board expands through its Open button (mouse or native keyboard activation) into **Todo / In progress / Completed**. Escape collapses it. Cards have Codex/Claude/Hermes/Antigravity/SORA/unassigned colours and readable assignee/run-status labels; high contrast uses system colours rather than colour-only meaning. Narrow views retain three lanes with horizontal scrolling. Mode and logical placement are UI-only preferences; note text/selection/submission keys remain process-local.

**Add note** saves planned work, not an agent run. **Assign**, **Move** and **Remove** use canonical board versions. Manual placement in Completed does not claim a successful run; removal hides the note and retains task/run history. **Start planned** opens the shared exact-provider/model/project selector, whose explicit selection determines actual execution; assignment colour is not entitlement. Claude assignment does not imply a configured Claude executor. Run/retry acknowledgements represent admission, not a successful result; inspect Activity for evidence.

An uncertain Add retains its body/key/assignee/Core identity; **Restore submitted draft** restores that exact process-local draft for explicit retry. A confirmed note is not recreated while finishing its assignment. Concurrent assignment/version changes require inspection, not overwrite. An unknown non-idempotent Retry cannot be replayed in that host session; inspect canonical task/run evidence before further work. These guards do not promise durable uncertain-request reconciliation after host restart.

Content lists Core-registered references and shows inert exact IDs/paths/handler metadata. **Open / Show / Where** revalidates the selected reference and calls Core's supported navigation handler; no arbitrary path, URL or executable is launched by the client. Actual unsupported/failure/limitation results remain labelled; malformed/mismatched acknowledgements are unknown outcomes, not success. Integrations is a read-only metadata/capability/active-extension/provider-status inspector, not a configuration or permission editor. Declared historical/remote grant metadata does not reintroduce local companion approval prompts.

All three views share the existing host connection and narrow cached projections, hide on user close, retain transient state, mark stale/offline data and disable effects independently of model readiness. No new panel timer/store/runtime is created. Pending board/selector/navigation work prevents host Quit. UI version1 now recognizes ten panel keys and `board_expanded`; old stores without the field remain valid, while older binaries encountering unsupported new fields/keys preserve them read-only. Canonical AppSettings remains v9.

## Task attempts, registered files and recent activity

The shared-host Chat now shows up to8 compact buttons for recent public task/run activity. Each button opens its exact canonical task in Activity; the tooltip keeps source/event/sequence/task/run/correlation/time. These are recent task events, not an inferred link to a particular Chat message. Completed means a validated provider report, not independent verification of every reported action. Private event payloads are never rendered.

In Activity, select a task or enter a known **Exact task ID** and choose **Inspect task ID** to access a record outside the latest100 list. Open **All attempts / files**, then **Refresh attempts**. Pages contain up to50 attempts; Next reads older attempts, Previous returns through the visited pages. Refresh starts a new newest-first view including later admissions. Attempt states are read snapshots; refresh explicitly to see changes. Select an attempt and **Inspect attempt** for that exact report, timestamps, outcome, coverage and any bounded-output omissions. Missing results remain explicitly missing; a newer task result is not substituted.

Reported files/changelog paths appear as inert text. **Open registered file** is enabled only for a selected Core-issued content reference from the inspected attempt. It rechecks registration and uses Core's configured handler/static policy. Unregistered, relative, truncated or missing paths cannot be launched directly. An unsupported/limited/failure or unconfirmed acknowledgement is shown honestly, with no automatic replay. Registration is scoped to owner/device/project and may expire; reported file existence/effects are not promised.

History reads work with the dialogue model down when the matching Core is available. Disconnect/epoch change prevents old reads becoming current and disables Open; returning online alone does not make an old inspected report current. Explicit inspection is required again. Selection/drafts remain process-local, not canonical settings/history duplicates. Closing Activity hides it; existing host Quit guards cover pending navigation.

These controls have component and deterministic HTTP verification, **not native user-side acceptance yet**. The earlier policy-rejected GUI setup was not bypassed. See [attempt-history verification](../verification/GUI1_RUN_HISTORY_GPT-6.1-Sol_2026-10-04.md). GUI-1c remains in progress, full Settings/voice and broader native acceptance remain roadmap work, and the ordinary Desktop default is unchanged.

## Canonical Memory browser

Open **Memory / retained context** from tray/command menu/Chat More, use the Settings Memory link, or pass `-Client Shell -ShellPanel memory`. The matching Core must include the new owner-local browser routes; an older running Core reports unavailable and is not restarted automatically. No model call or microphone is needed to browse.

**Overview** shows active current-project plus owner-global records. **Search / Refresh** performs literal remembered-word search, with state/project and exact-scope filters. This is not semantic relevance search. Pages show50 records with Previous/Next; Refresh starts a new admission ceiling. Select a row or enter an exact Memory ID to inspect real content/version/scope/sensitivity/retention/provenance/expiry. Superseded records remain their exact original IDs; they do not silently redirect. Deleted/unknown/out-of-scope records are absent. Creation date, importance/relevance and graph relations are not invented; Graph is labelled unavailable.

Only current scoped registered evidence is linked. Private capture IDs/files/rationale/reasoning and unregistered paths are withheld. **Open registered evidence** rereads the exact memory, then uses Core's existing reference navigation/static policy and reports the captured reference's actual outcome; it never executes raw path/text. It requires a current connected memory/detail/registration and is disabled offline or while host/effects are blocked. Opening an inspector is not yet an acknowledged conversational `present_memory` action.

Close hides Memory; query/page/selection and any correction draft remain process-local. Disconnect marks caches stale; reconnect alone cannot confirm them, and a new Core clears old browsing targets/cursors while retaining pinned drafts. Refresh/Inspect is explicit. No memory/query/capture/draft/request content is stored in UI preferences; only `memory` placement is stored (12 recognized panel keys, storev1). [Browser contract](../gui/GUI3_MEMORY_BROWSER_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [browser acceptance limits](../verification/GUI3_MEMORY_BROWSER_GPT-6.1-Sol_2026-10-04.md).

**Correct…** drafts an exact active record/version. **Save correction** creates a successor without changing expiry or presenting old capture evidence as evidence for your new text. The draft pins its original ID/version/Core; browsing cannot retarget it. Conflicts retain authored text. **Review latest** displays the same exact record and asks whether to adopt that baseline while keeping your text. Superseded/expired records cannot be corrected; discard and explicitly inspect a successor if that is what you intend.

**Forget…** confirms the exact record/version. It removes only that ID from canonical retrieval/browser results, not its other versions, captures, conversation, audit, backups or agent transcripts. It is soft deletion; there is no Undo or physical-erasure guarantee. Private captures continue through existing retention. To forget a successor, inspect and forget that exact ID separately.

On an uncertain response, the request/text/key stays frozen. **Check receipt** reads historical confirmation without another write, including after a Core instance change. **Retry same request** explicitly uses the identical captured request against its original current Core; no automatic replay. A missing receipt is not proof no write occurred. **Discard draft** warns that discarding is not undo and displays the unresolved UUID. Hide preserves drafts; native Quit protects pending edits/modals and asks before discarding unsaved drafts, while IPC Quit refuses them. Drafts are not recoverable after host restart. Confirmed edits mark browsing stale: Refresh and explicitly inspect any successor before treating it as current state.

These GUI-3b controls are implemented in source/component tests, not native interaction acceptance. Existing running older Core must be normally restarted later to expose mutation routes; no automatic restart is performed. [Management contract](../gui/GUI3_MEMORY_MANAGEMENT_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [verification](../verification/GUI3_MEMORY_MANAGEMENT_GPT-6.1-Sol_2026-10-04.md). GUI-3c conversational presentation now has later source integration described below, but final-source/native/live acceptance remains open; real graph/final design remains GUI-5.

## Shared Voice controls and microphone indication

Open **Voice / microphone** from Chat More, the tray or command menu. Attach-only `--show voice` and root/full `-Client Shell -ShellPanel voice` summon the same profile host. Opening Voice performs no audio Start. The host reads Core's local voice status on its existing refresh loop even when Chat/Voice are hidden.

**Start voice** loads existing local speech assets; it does not open capture. Hold the button with the left mouse button or focused Space to record; release sends finalized speech. Holding again uses existing barge-in behavior. Focus/capture loss or hiding while held requests Stop/discard rather than sending that recording. The controller retains release/loss intent if Begin acknowledgement is still pending and does not retarget a held episode to a different Core. Physical event delivery and network closure latency are not yet accepted.

**Stop speaking only** silences output while preserving generation/capture. **Stop voice response** discards capture and cancels that voice turn; it is not Chat Stop or independent-task cancellation. **Close audio worker** explicitly closes the Core-owned local audio service. Closing the panel otherwise only hides it. Quit refuses held/pending voice work. External Core ownership is unchanged.

Tray text/icon show **Mic ON**, **Mic closed · worker report**, or **UNKNOWN** from explicit capture metadata/current connection. In-flight or failed actions and stale/older Core status do not imply Closed. The panel also shows independent dialogue-model readiness: speech Ready does not prove a working LLM. Network failure may prevent confirmation of release/Stop; use explicit Close audio when possible. Core's configured2–60-second recording limit bounds capture, but this is not a claim of instantaneous physical closure on GUI release.

Actual device keys/channels/adapter indices are read-only inventory in Voice. Ambiguous duplicate keys are displayed rather than silently chosen. Canonical voice paths/device/voice/speed/recording settings remain in AppSettings and can now be edited in the categorized Settings/device picker; native/physical persistence acceptance is still open, and there is no new voice-local settings file.

UI preferencev1 now recognizes12 panel placements including `voice` and `memory`. Existing stores remain valid; unsupported older binaries preserve unknown new keys read-only. AppSettings remainsv9. [Shared voice evidence](../verification/GUI1_VOICE_GPT-6.1-Sol_2026-10-04.md) is component/HTTP verification, **not native or human-spoken acceptance**. No owner audio was started during verification.

## Store, migration and conflicts

Readable, indented UI JSON lives at:

```text
<state-root>/desktop-shell/preferences.json
<state-root>/desktop-shell/backups/
<state-root>/desktop-shell/runtime.json
```

Version 1 stores theme/text/motion/compact/pin/shortcut/detail choices, logical outer panel bounds relative to monitor work areas, monitor identity/DPI and legacy import provenance. Core AppSettings remains canonical for model/access/voice/agent settings. There is no competing settings or conversation database.

`runtime.json` is a separate readable version-1 discovery hint: profile/endpoint, token-file path (not its contents), host identity and launcher PID/start time/session metadata. It is not shutdown authority or an editable settings store. Invalid/changed/ambiguous hints block managed launch and remain preserved. Saves hold a cooperating-writer lock across fingerprint validation/atomic replacement; lock contention fails visibly without replacing the hint. Stopped descriptors retain the last Core epoch. A live or unverifiable previous launcher prevents duplicate startup; after host loss, a reachable Core may be authenticated and attached but its shutdown ownership is not silently adopted.

On first creation, only recognized profile-local `widget/settings.json` and `desktop/settings.json` are imported. Successful import preserves original bytes and dated byte-identical backups, records hashes and is not repeated over later host edits. Quiet/topmost/selected-tab legacy choices remain inspectable metadata where corresponding new workflows are not yet implemented; physical coordinates without recorded DPI use a clamped best-effort first placement.

UTF-8 files with or without a byte-order mark are supported, including the existing widget writer's format. Hashes/backups preserve the encoding marker rather than rewriting the original file.

For an explicitly chosen legacy file elsewhere, add `--legacy-widget-file PATH` and/or `--legacy-desktop-file PATH` on the first profile-host launch. Global AppData files are not automatically read into every profile. Unrecognized files/fields are ignored with diagnostics rather than copied as canonical configuration or secrets.

Saves use validation, revisions, a cooperating-writer file lock, disk fingerprint checks, a flushed temporary file and atomic replacement. A competing edit retains the UI draft and requires explicit reload/reconciliation. Moving a panel alone is merged with an appearance draft; competing appearance changes are not silently overwritten. Reload is explicit and does not auto-resend a Core effect.

Corrupt/unknown-version preferences remain untouched and read-only, with safe UI defaults **in memory only**. Save/reset are disabled. Owner-invoked recovery confirms replacement and preserves the original in a dated backup first. Oversized, inaccessible or ambiguous linked files may require owner filesystem repair; the GUI reports the failure rather than bypassing the file check. This operation repairs only UI preferences, not canonical Core configuration.

## Current acceptance limits

The managed lifecycle channel is now connected to the host/root Shell path. `GET /api/v1/runtime/lifecycle` is an authenticated owner-local projection, not stop authority. `POST /api/v1/runtime/shutdown` additionally requires ephemeral launch authority and exact session/instance/request correlation; normal/external Cores refuse it. Credentials are not stored in UI JSON or exposed as editable values. [Control foundation](../verification/GUI1_LIFECYCLE_CONTROL_GPT-6.1-Sol_2026-10-03.md) and [managed-host verification](../verification/GUI1_MANAGED_HOST_GPT-6.1-Sol_2026-10-03.md) distinguish component checks from actual isolated native startup/repeat/hide/Quit evidence. Tests used a deterministic backend with no inference/avatar/voice; model-unavailable UI was truthful, not a live model reply.

Quit has a deadline covering initialization cancellation as well as control/exit/absence waits. Unresponsive initialization keeps recovery alive; canceled initialization cannot later launch a child or record attachment. A pending Quit now waits for the exact owned Core API to become ready within that deadline, with host effects blocked, then shuts it down gracefully. This does not interrupt a long build/model load immediately: if the API never arrives before timeout, recovery remains open with ownership retained. No immediate pre-API cancellation channel or force-kill fallback exists yet. [Startup-Quit evidence](../verification/GUI1_STARTUP_QUIT_GPT-6.1-Sol_2026-10-04.md) distinguishes late-readiness component fixtures from native normal-Quit proof. Host-loss races and broader actual failure/physical acceptance remain required before GUI-1a closes.

Actual native evidence covers a 144-DPI Windows environment, offline controls, live system colours/150% text, compact/draft behavior, moved bounds, normal restart, alternate shortcut summon and corrupt-file no-write diagnostics. Geometry tests cover 100/150/200%, negative origins and tiny/removed work areas; these are **not physical mixed-monitor tests**.

Broader managed lifecycle acceptance, fullscreen/sleep/monitor-loss, physical high contrast/screen reader/OS text scaling, native acceptance of full Settings/retained surfaces/Memory/Voice, positive native attachment reading, physical keyboard/IME, history selection/scroll anchoring and final visual styling remain roadmap work. Memory correction/forget and presentation transport have recorded component proof but still need native acceptance; later conversational source needs final-source verification. Scheduler and real graph remain implementation work. See [preference verification](../verification/GUI1_PREFERENCES_GPT-6.1-Sol_2026-10-03.md), [initial Chat verification](../verification/GUI1_CHAT_GPT-6.1-Sol_2026-10-04.md) and the [root roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md).
## GUI-3c semantic Memory presentation source checkpoint

**2026-10-04 10:01:58 +01:00, GPT-6.1 Sol:** The opt-in Shell now renews/polls the Core's Memory-only host registration through its existing shared refresh. A valid queued exact-ID/version request can inspect/select/static-highlight the canonical record without activating the window; drafts/modals/effects, stale identity/version, dismissal/minimize and expiry defer or reject it. Only a matching actual host acknowledgement can publish selected/already-visible. Other outcomes and lost transport are not success. [Contract and routes](../gui/GUI3_MEMORY_PRESENTATION_CONTRACT_GPT-6.1-Sol_2026-10-04.md), [component/HTTP verification and limits](../verification/GUI3_MEMORY_PRESENTATION_GPT-6.1-Sol_2026-10-04.md).

**Historical checkpoint boundary:** The preceding paragraph preserves the transport verification. The later source reconciliation below supersedes the then-unconnected model/retrieval/chip status without extending those earlier passing totals. Compatibility clients/default Desktop remain unchanged. A pending request is not a visible panel; an event is a host report, not independent Windows attestation.

### Current conversational source — documentation reconciliation

**2026-10-04 10:34:25 +01:00, GPT-6.1 Sol:** The inspected source now connects `find_memory` literal canonical lookup and `present_memory` using turn-local issued references, context-selection events, host-acknowledgement-aware responses and Memory evidence chips. Presentation is enabled for explicit owner requests, not quoted memory instructions. Retrieval chips report canonical context selection, not model thoughts; selection chips label the host report, not current visibility. Clicking a chip requests its recorded exact ID/version and must revalidate it rather than follow a successor.

That paragraph preserves the documentation-only checkpoint. **Later source/component verification:** [companion contract](../gui/GUI3_MEMORY_COMPANION_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [final verification](../verification/GUI3_MEMORY_COMPANION_GPT-6.1-Sol_2026-10-04.md) record104 focused Python checks,369 C# passes and full811-Python/25-skipped/8-PWA regression plus client builds. These do not certify native GUI interaction or a real model. An older running Core may lack the new routes/behavior; no automatic restart is authorized by this update. Follow [roadmap §4.29 and GUI-3c](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) for connected acceptance before relying on the conversational path. Real graph, scheduler, ordinary-launch replacement and prior physical/native gates remain open.

## Automations availability — storage source checkpoint

**2026-10-04 12:48:42 +01:00, GPT-6.1 Sol:** Matching new Core source has owner-local Automation storage/history/receipt routes and migration12. Creates default paused; exact-version save/pause/resume/delete is canonical and receipt-backed. These routes explicitly report **scheduler unavailable**. Saving an active definition or an internal reserved occurrence is not agent execution. No Automations GUI entry or operative Run now is delivered yet; do not use the reference image as a screenshot of this implementation. See the [storage contract](../gui/GUI4_AUTOMATION_STORAGE_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [verification](../verification/GUI4_AUTOMATION_STORAGE_GPT-6.1-Sol_2026-10-04.md).

The current owner Core was not restarted/migrated; these source changes are not loaded automatically. Next is the Core-owned worker with actual task/run admission/recovery, then the shared reference-based panel. Existing Settings/local-policy defaults, UI-only preferences, compatibility clients/default Desktop and all prior native/live/physical gates remain unchanged.

## Automations worker — later source checkpoint

**2026-10-04 13:23:16 +01:00, GPT-6.1 Sol:** Matching current source now owns a bounded Automation timing worker and routes occurrences through existing canonical task admission/recovery. Current list/detail report actual running/degraded/stopping/stopped/unavailable state; durable save receipts retain their historical state. Saved active definitions can now admit real tasks when due and policy/provider/project validation permits them. Creates still default paused. Unknown outcomes are not retried and block overlap; pause prevents future admission, not cancellation of an already-admitted task.

The preceding storage-only checkpoint is historical. [Worker contract](../gui/GUI4_AUTOMATION_WORKER_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [verification](../verification/GUI4_AUTOMATION_WORKER_GPT-6.1-Sol_2026-10-04.md) distinguish actual temporary Core/task/HTTP tests from missing live-provider/native acceptance. **No Automations panel or manual Run now endpoint yet.** Next is durable manual Run now, then shared reference-based List/Overview/Edit/Logs and task/evidence controls. Do not infer availability from a screenshot or historical receipt.

Owner Core/data/environment/settings were not restarted/migrated or reloaded. The older currently running Core does not gain these changes automatically; no owner restart is implied by this implementation checkpoint. Existing default Desktop, settings/UI preference versions and inherited GUI gates remain unchanged.

## Automations manual Run now — later source checkpoint

**2026-10-04 13:44:05 +01:00, GPT-6.1 Sol:** Matching new Core source now implements owner-local `POST /api/v1/automations/{id}/run-now` with current instance, stable request UUID and expected definition version. Uses exact saved behavior for active/paused definitions, without changing state/version/next scheduled slot. New202/duplicate200 means a durable attempt, not completed work. Overlap skips; unavailable worker blocks. Unadmitted requests expire after five minutes. Inspect canonical occurrence history for current task/run status and reconcile lost responses through the original request receipt before any explicit same-key retry.

[Manual contract](../gui/GUI4_AUTOMATION_MANUAL_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [verification](../verification/GUI4_AUTOMATION_MANUAL_GPT-6.1-Sol_2026-10-04.md) supersede the preceding then-missing endpoint wording, not its historical results. **No shared Automations window or native Run now button is delivered yet.** Next shared List/Overview/Edit/Logs/full retained editor and task/evidence/semantic controls. Owner Core/data/settings/environment remain unchanged; no owner restart/migration or live/native acceptance is implied.

