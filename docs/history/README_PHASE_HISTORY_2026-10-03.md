# SORA README as of 2026-10-03 — phase-by-phase history

This is the complete previous root README (last modified 2026-10-03 01:04 +01:00), replaced by a shorter front page.

> Moved verbatim on 2026-10-05 by Opus 5.5 during the documentation restructure.
> No wording, dates, figures or attributions were changed; only relative link
> paths were adjusted so they still resolve from this folder.

SORA (Spatial Operator for Recursive Antics) is a Windows-local agent runtime under active
development. The current G1 text core provides durable identity/history, bounded context, concurrent
deterministic dialogue and reasoning tasks, validated results/patches, recovery, tracing, and a CLI.

The default provider is a hermetic deterministic mock. Hermes ACP is also available as an explicit
external provider adapter; it requires the Hermes installation and configured credentials. Runtime
state, credentials, local validation artifacts, backups, and provider installations are not committed.

## Bootstrap and verify

On Windows PowerShell, with `uv` available:

```powershell
.\scripts\bootstrap.ps1
.\scripts\verify.ps1
```

Inspect a fresh local runtime with:

```powershell
uv run --locked python -m sora --state
```

Run one deterministic background task and wait for its grounded result:

```powershell
uv run --locked python -m sora --once "Analyze the deterministic fixture." --wait
```

Run through the installed Hermes ACP backend when it is configured:

```powershell
uv run --locked python -m sora --provider hermes --hermes-cwd C:\path\to\isolated\workspace --once "Analyze the repository." --wait
```

The Hermes adapter launches one `hermes acp` process per SORA run, requests a structured JSON
result, and converts facts/memory updates into validated SORA patch proposals. An explicit existing
`--hermes-cwd` assigns its workspace. Hermes retains its native tools and configured MCP integrations
by default, and ACP permission requests select `allow_once`; use `--hermes-deny-approvals` or
`--hermes-skip-configured-mcp` for an explicitly restricted run. SORA does not implement ACP
client-side editor filesystem/terminal methods, which is separate from Hermes' own tools. Native
session resume and cancellation are mapped; steering is not. `hermes acp --check` verifies the local
ACP installation without starting a model run.

Run a bounded read-only Codex task with the cost-sensitive default model:

```powershell
uv run --locked python -m sora --provider codex --codex-cwd C:\path\to\repository --once "Inspect README.md." --wait --task-timeout 120
```

The Codex adapter uses the documented App Server protocol, defaults to GPT-5.6 Luna at low effort,
preserves native thread identity across resume, and maps interruption and activity into SORA's
provider lifecycle. The direct CLI is deliberately read-only. Coding writes require an owned Git
worktree plus a live `GitWorkspaceManager` lease; the adapter rejects unowned `workspace-write` and
all `danger-full-access` runs.

Run an auto-routed coding write in a managed worktree from an explicit base:

```powershell
uv run --locked python -m sora --provider codex --codex-cwd C:\path\to\repository --codex-write-base HEAD --codex-workspace-root C:\path\to\sora-workspaces --once "Edit the requested files and run focused tests." --wait --task-timeout 300
```

The source checkout is not changed. SORA retains the worktree and a review artifact containing the
base, head, status, diff, commands/tests, and uncertainties; it never merges the result automatically.

Start the interactive mock CLI with `uv run --locked python -m sora`. Its commands are:

```text
/task TEXT
/tasks
/state
/messages
/wait TASK_ID
/cancel TASK_ID
/retry TASK_ID
/quit
```

Direct conversation can use a separate OpenAI-compatible model without changing the reasoning
provider. For example, with a model already loaded in a loopback LM Studio server:

```powershell
uv run --locked python -m sora --dialogue-backend openai-compatible --dialogue-model your-loaded-model-id --dialogue-base-url http://127.0.0.1:1234/v1
```

Replace the model identifier with the one reported by your server. For an HTTPS provider that
requires a key, set `SORA_DIALOGUE_API_KEY` in the process environment; do not put the key in the
command line. `--provider` continues to select Hermes, Codex, Antigravity or deterministic
background reasoning independently. The authenticated API, PWA and voice sessions use the same
configured direct-dialogue path. Core supplies bounded identity/history and, for relevant requests,
a read-only task-status snapshot selected through the capability resolver. Remote dialogue sessions
receive history and task status only when their paired scopes also include `conversation:read` and
`tasks:read`, respectively. The settings projection reports backend/model/endpoint and whether a
key is configured, never the key itself. Choosing a nonlocal model endpoint sends the selected
identity, recent conversation and relevant task-status context to that endpoint. The default
remains an offline deterministic dialogue fixture; provider errors fail the turn without storing
a partial conversation pair.

Fault behavior is available for hermetic checks through `--mock-fault`; use `--help` for the
currently supported modes and `--mock-delay` to inject latency. By default, canonical state is kept
under `data/` at the selected `--root` and remains ignored by Git.

The engineering roadmap and verified progress are maintained in
[`SORA_IMPLEMENTATION_PLAN.md`](../../SORA_IMPLEMENTATION_PLAN.md).

P03 evidence and explicit limitations are recorded in
[`docs/verification/P03_TEXT_RUNTIME_2026-09-07.md`](../../docs/verification/P03_TEXT_RUNTIME_2026-09-07.md).

Completed P04 Hermes live-adapter evidence and limitations are recorded in
[`docs/verification/P04_HERMES_LIVE_2026-09-08.md`](../../docs/verification/P04_HERMES_LIVE_2026-09-08.md).
The earlier credential-free implementation record remains at
[`docs/verification/P04_HERMES_ADAPTER_2026-09-07.md`](../../docs/verification/P04_HERMES_ADAPTER_2026-09-07.md).

Current P05 Codex/App Server and worktree evidence is recorded in
[`docs/verification/P05_CODEX_APP_SERVER_2026-09-08.md`](../../docs/verification/P05_CODEX_APP_SERVER_2026-09-08.md).

Phase 10 is complete. SORA now has a bounded read-only Windows/UIA bridge, volatile and
revalidated desktop targets, attention/reference continuity, configured shell-free content
handlers, exact navigation authority, and separately authorized spatial presentation. Run its
native acceptance matrix with `.\scripts\verify-p10.ps1 -Full`. The implementation boundaries,
live privilege evidence, remaining non-P10 limitations, and contributor attribution are recorded in
[`docs/verification/P10_PHASE_COMPLETION_GPT-5.6-Sol_2026-09-14.md`](../../docs/verification/P10_PHASE_COMPLETION_GPT-5.6-Sol_2026-09-14.md).

Phase 11 is complete. P11.1 adds data-driven semantic presentation profiles and procedural reach;
P11.2 adds the generic registered-action lifecycle and atomic presentation ownership; P11.3 adds
exact-grant, contact-revalidated and journaled PRESS. P11.4 connects the packaged Unity player to a
Core-held prepared interaction and records walk/align/reach/contact/invoke/verify/retract while an
independent deterministic media clock changes from playing to paused. P11.5 registers logical TYPE
without changing the generic controller or POINT/PRESS: Core retains text and authority, a bounded
UIA ValuePattern worker verifies the exact ordinary-field value, and cancellation/duplicate cases
remain explicit and non-replayed. See
[`docs/verification/P11_ANIMATION_IK_PRESENTATION_GPT-5.6-Sol_2026-09-15.md`](../../docs/verification/P11_ANIMATION_IK_PRESENTATION_GPT-5.6-Sol_2026-09-15.md).
P11.2's lifecycle evidence is in
[`docs/verification/P11_ACTION_REGISTRY_LIFECYCLE_GPT-5.6-Sol_2026-09-15.md`](../../docs/verification/P11_ACTION_REGISTRY_LIFECYCLE_GPT-5.6-Sol_2026-09-15.md).
P11.3's native action and no-replay evidence is in
[`docs/verification/P11_AUTHORIZED_PRESS_GPT-5.6-Sol_2026-09-15.md`](../../docs/verification/P11_AUTHORIZED_PRESS_GPT-5.6-Sol_2026-09-15.md).
The packaged Pause recording is described in
[`docs/verification/P11_PAUSE_DEMO_GPT-5.6-Sol_2026-09-16.md`](../../docs/verification/P11_PAUSE_DEMO_GPT-5.6-Sol_2026-09-16.md),
and logical TYPE evidence is in
[`docs/verification/P11_LOGICAL_TYPE_GPT-5.6-Sol_2026-09-16.md`](../../docs/verification/P11_LOGICAL_TYPE_GPT-5.6-Sol_2026-09-16.md).

P09 is now complete: P09.4 distinguishes the actual detected two-monitor layout from synthetic
resolution, DPI, hotplug, work-area and unavailable/resume transition fixtures, with safe avatar
relocation and no claim that this run changed physical display or power settings. Phase 12 has begun;
P12.1 adds collider-anchored native grab/drag/release, physical-pixel spring/damping, bounded release
inertia and capture-loss cleanup while retaining blank-area click-through. See
[`docs/verification/P09_TOPOLOGY_TRANSITIONS_GPT-5.6-Sol_2026-09-16.md`](../../docs/verification/P09_TOPOLOGY_TRANSITIONS_GPT-5.6-Sol_2026-09-16.md)
and
[`docs/verification/P12_GRAB_RELEASE_GPT-5.6-Sol_2026-09-16.md`](../../docs/verification/P12_GRAB_RELEASE_GPT-5.6-Sol_2026-09-16.md).

P12.2 adds one-owner simple falling after grab release, bounded gravity and frame substeps,
work-area-bottom supports, air/ground damping, finite-state recovery, and runtime-only SpringBone
tuning. One hundred deterministic drag/drop cycles settle cleanly; the packaged avatar performs a
real 160-pixel lift and Core-observed landing while 28 licensed-VRM spring joints are tuned through
UniVRM's supported runtime API. See
[`docs/verification/P12_SECONDARY_MOTION_FALLING_GPT-5.6-Sol_2026-09-17.md`](../../docs/verification/P12_SECONDARY_MOTION_FALLING_GPT-5.6-Sol_2026-09-17.md).

P12.3 adds a bounded 12-joint screen-plane ragdoll/recovery owner with finite joint limits,
front/back/side orientation and settle detection, smooth get-up blending, timeout restoration and a
shared full-body pose lease. Hard P12.2 landings can enter recovery, while idle, gaze, presentation,
IK, grab and falling yield to the recovery owner. The bundled and packaged VRM recovers all four
fall planes and releases the lease after each run. See
[`docs/verification/P12_RAGDOLL_RECOVERY_GPT-5.6-Sol_2026-09-17.md`](../../docs/verification/P12_RAGDOLL_RECOVERY_GPT-5.6-Sol_2026-09-17.md).

P12.4 adds topology-derived monitor/taskbar supports and at most 32 explicitly selected,
short-lived window-top surfaces. Selected surfaces contain no window title or content, follow moves,
and invalidate on minimize, close, occlusion, omission, expiry or moving out from under the avatar.
The packaged player received a Core-delivered snapshot and fell predictably from each unavailable
window state to the actual taskbar. See
[`docs/verification/P12_WINDOW_SURFACES_GPT-5.6-Sol_2026-09-17.md`](../../docs/verification/P12_WINDOW_SURFACES_GPT-5.6-Sol_2026-09-17.md).

P12.5 reports physical transition edges rather than continuously inferring behavior: grab/release,
click/poke, fall/land, support removal and interaction completion/failure. Unity and Core apply
independent cooldown, deduplication, terminal-uniqueness, burst and retention bounds. The packaged
Core received 26 events across all seven exercised physical kinds. See
[`docs/verification/P12_SEMANTIC_FEEDBACK_GPT-5.6-Sol_2026-09-17.md`](../../docs/verification/P12_SEMANTIC_FEEDBACK_GPT-5.6-Sol_2026-09-17.md).

P12.6 connects Core-owned desktop objects to the existing embodiment vocabulary through one scoped,
capacity-bounded bridge. Visible advertised affordances resolve lazily through the capability resolver;
exact object/verb grants map look, point and touch to existing gaze, marker and P11 lifecycle commands.
Hidden/private objects are absent from unauthorized projections and action resolution, while failed or
revoked presentation cannot mutate canonical object state. The packaged player completed all three
verbs and retained canonical version 1. See
[`docs/verification/P12_DESKTOP_OBJECT_AFFORDANCES_GPT-5.6-Sol_2026-09-18.md`](../../docs/verification/P12_DESKTOP_OBJECT_AFFORDANCES_GPT-5.6-Sol_2026-09-18.md).

P13.1 adds content-free Windows desktop-event awareness for foreground, window and dialog lifecycle
changes plus Core-owned task transitions. Exact-scope reusable authority starts the native subscription;
every callback is rechecked, event IDs and semantic bursts are bounded/deduplicated/debounced, and one
burst invalidates volatile attention and spatial references without starting inference or speech. The
event envelope cannot contain titles, text, pixels or UIA contents. See
[`docs/verification/P13_DESKTOP_EVENT_AWARENESS_GPT-5.6-Sol_2026-09-18.md`](../../docs/verification/P13_DESKTOP_EVENT_AWARENESS_GPT-5.6-Sol_2026-09-18.md).

P13.2 adds explicit one-shot capture without creating an always-on vision service. A region request is
limited to one exact on-display rectangle; a window request is bound to an existing P10 desktop target
and its process-start/window identity. A killable helper returns one bounded PNG in memory, while Core
rechecks grant and topology state, rejects widened or stale frames, and retains at most eight frames for
at most 30 seconds under owner/device/project scope. Revocation cancels an in-flight helper and no
capture is sent to a model automatically. See
[`docs/verification/P13_SCOPED_CAPTURE_GPT-5.6-Sol_2026-09-18.md`](../../docs/verification/P13_SCOPED_CAPTURE_GPT-5.6-Sol_2026-09-18.md).

P13.3 normalizes detector output into short-lived, owner/device/project-scoped evidence with exact
frame-to-screen mapping, capture/detector provenance, confidence disposition and capture-capped
expiry. Evidence is process-memory only. Every record explicitly denies action authority,
instruction authority and automatic canonical-fact status; low-confidence and instruction-like text
remain inspectable but cannot enter context as candidates. Run the repeatable local capability demo:

```powershell
uv run --locked python scripts/demo-capabilities.py --output docs/verification/p13-vision-evidence/demo.json
```

The demo uses deterministic fixture pixels and no external provider or native OS action, while still
exercising Core dialogue, task routing, projections, event policy, capture authorization and vision
normalization. See
[`docs/verification/P13_VISION_EVIDENCE_GPT-5.6-Sol_2026-09-18.md`](../../docs/verification/P13_VISION_EVIDENCE_GPT-5.6-Sol_2026-09-18.md).

P13.4 completes Phase 13 by joining P10's volatile circle targets to P13's capture/evidence path.
`POST /api/v1/attention/crop` accepts only an attention-target ID and capture ID—never caller geometry
or cursor samples—then derives the exact live circle bounds, refuses targets with a semantic UIA
identity, and uses the existing exact-region capture grant. The enriched reference can be reused by a
task. Only crop/evidence IDs and the minimal target rectangle enter the task snapshot; PNG bytes,
cursor trails and detector labels remain volatile. Usable P13.3 candidates can enter provider context
while low-confidence or instruction-like evidence remains excluded. See
[`docs/verification/P13_ATTENTION_CROP_GPT-5.6-Sol_2026-09-18.md`](../../docs/verification/P13_ATTENTION_CROP_GPT-5.6-Sol_2026-09-18.md).

P14.1 establishes measured local voice defaults on the actual reference machine before streaming
sessions are built. A repeatable isolated benchmark runs Silero VAD ONNX, faster-whisper base.en
CPU-int8 and Kokoro v1.0 ONNX-int8 in fresh processes, recording pinned model digests and licences,
cold/warm latency, resident memory, real-time factor and deterministic quality metrics. Optional voice
packages and downloaded models stay outside SORA Core's ordinary dependency set; LiveKit and cloud
speech services are not required. See
[`docs/verification/P14_VOICE_BENCHMARK_GPT-5.6-Sol_2026-09-18.md`](../../docs/verification/P14_VOICE_BENCHMARK_GPT-5.6-Sol_2026-09-18.md).

P14.2 adds authenticated streaming voice sessions without moving raw microphone audio into Core.
The client-local seam turns PCM frames into VAD/STT transcript events; Core retains partials only in
bounded memory, commits each finalized user utterance and assistant reply atomically, and returns an
expiring semantic playback command for local TTS. Durable utterance receipts make reconnect and
restart retries exactly once. Exact device generations prevent stale input/output events, output
recovery never recreates abandoned audio, and echo suppression applies only after playback has
actually started. The deterministic client fixture verifies the full semantic route, but P14.2 does
not claim that a real microphone or speaker was opened. See
[`docs/verification/P14_STREAMING_VOICE_SESSIONS_GPT-5.6-Sol_2026-09-19.md`](../../docs/verification/P14_STREAMING_VOICE_SESSIONS_GPT-5.6-Sol_2026-09-19.md).

P14.3 separates barge-in from output-only silence. Fresh client speech immediately aborts local
speaker output, resets the lip-sync presentation seam and sends an authenticated interruption event;
Core cancels the cooperative dialogue coroutine and invalidates its output epoch so no queued or
late audio can start. `stop_speaking` uses the same immediate local silence but lets reasoning finish,
atomically persists the resulting turn and suppresses playback. Callers must explicitly select
`cancel_response` when silence should also abandon reasoning. See
[`docs/verification/P14_BARGE_IN_GPT-5.6-Sol_2026-09-19.md`](../../docs/verification/P14_BARGE_IN_GPT-5.6-Sol_2026-09-19.md).

P14.4 derives mouth movement from the local synthesized PCM stream rather than language-model frame
commands. Ordered signed-16 PCM chunks feed a validated RMS/noise-gate/smoothing fallback and a
monotonic audio clock; presentation frames carry the playback ID and output epoch, so a late chunk
cannot animate a replacement turn. Playback commands contain only one coarse utterance emotion.
Unity maps mouth openness to the VRM `aa` expression and bounded emotion to standard VRM expressions,
then resets to neutral on pause, interruption, output-device loss, disconnect, failure or completion.
The frame type is client-local and is absent from Core's published schemas and embodiment command
registry. See
[`docs/verification/P14_MOUTH_EMOTION_SYNC_GPT-5.6-Sol_2026-09-19.md`](../../docs/verification/P14_MOUTH_EMOTION_SYNC_GPT-5.6-Sol_2026-09-19.md).

P14.5 aligns spoken references and conversational control. STT adapters may attach the timestamp of
the actual deictic phrase; Core resolves the volatile cursor buffer at that timestamp, not when the
final transcript arrives. Missing timing, missing retained history or missing observation authority
returns a durable clarification without guessing or calling the dialogue model. Explicit spoken
control is classified into output-only stop, named-task steering, named-task cancellation, separate
new work or ordinary dialogue. The client silences local audio immediately at speech onset but waits
for the first transcript hypothesis before choosing output-only stop versus full barge-in. See
[`docs/verification/P14_SPEECH_REFERENCE_INTENT_GPT-5.6-Sol_2026-09-22.md`](../../docs/verification/P14_SPEECH_REFERENCE_INTENT_GPT-5.6-Sol_2026-09-22.md).

P15.1 adds a responsive, installable local PWA served directly by SORA Core. Start Core and write its
fresh bearer token to a private local file:

```powershell
uv run --locked sora --root .local/runtime --identity-root identity --serve `
  --api-token-file .local/sora-api-token
```

Open `http://127.0.0.1:8765/app` and enter the token printed by Core or read it from the configured
token file. The token remains only in page memory: the PWA does not put it in a URL, local storage,
IndexedDB or the service-worker cache. The installed shell works offline, but messages, tasks,
projections, traces, health and readiness are deliberately network-only. After a disconnect, the
client pages through authenticated durable events and then refreshes authoritative projections;
expired, missing or future cursors force a full resynchronization. Conversation is primary, while
tasks/agents, steer/cancel controls and a payload-free connection trace remain secondary. The Mic
button uses the browser's speech-recognition service when available and visibly warns that it may not
be local; use the P14 client pipeline when local audio processing is required. See
[`docs/verification/P15_LOCAL_PWA_GPT-5.6-Sol_2026-09-22.md`](../../docs/verification/P15_LOCAL_PWA_GPT-5.6-Sol_2026-09-22.md).

P15.2 adds an opt-in second listener for paired private devices. The owner listener remains HTTP on
loopback and its bearer token is rejected by the remote listener. Remote access requires a concrete
private, link-local or overlay IP, a certificate/key pair, and at least one exact HTTPS browser
origin; wildcard or public addresses and plaintext remote HTTP fail closed. For example:

```powershell
uv run --locked sora --root .local/runtime --identity-root identity --serve `
  --api-token-file .local/sora-api-token `
  --api-remote --api-remote-host 192.168.1.20 --api-remote-port 8766 `
  --api-tls-certificate C:\private\sora-cert.pem `
  --api-tls-private-key C:\private\sora-key.pem `
  --api-remote-origin https://192.168.1.20:8766
```

The certificate must be trusted by the phone/browser and cover the configured host or IP. Never use
the committed `tests/fixtures/tls` certificate outside automated tests. Open the local `/app` with
the owner token to create a short-lived, one-time pairing code, then open the remote HTTPS `/app` on
the phone and claim it. The paired device credential is stored only in that origin's IndexedDB and
is exchanged for short-lived, memory-only `SoraSession` credentials. Sessions are limited to the
scopes selected when the code was created; task control is not in the default scope set. Revoking a
device from the local owner panel atomically revokes its active sessions.

Private-network reachability is not authority: unpaired clients, the owner bearer, expired sessions,
revoked devices, wrong origins/hosts, unlisted routes and scope escalation all fail. Remote WebSocket
upgrades are disabled; the browser uses authenticated bounded HTTP replay with payload-free remote
events. Pair/session attempts and general requests are rate-limited, and a bounded redacted audit is
available only through the loopback owner boundary. The implementation and deterministic TLS
fixtures pass, but physical phone/certificate-trust acceptance is still pending, so P15.2 remains in
review. See
[`docs/verification/P15_PRIVATE_REMOTE_TRANSPORT_GPT-5.6-Sol_2026-09-22.md`](../../docs/verification/P15_PRIVATE_REMOTE_TRANSPORT_GPT-5.6-Sol_2026-09-22.md).

P15.3 packages the Windows application as a hashed portable bundle with its own CPython runtime,
self-contained observation/action/type/capture helpers, Unity player and identity/PWA assets. The
installer uses versioned software and state slots so update can back up and migrate a clone before
atomically switching; rollback selects the previous release/state pair without downgrading a newer
database. Uninstall retains personal state by default, while `-PurgeData` is an explicit marker-
guarded operation. Optional per-user startup contains paths but no credential. Build and operating
instructions, asset/model boundaries and exact personal-data handling are documented in
[`SORA_INSTALL_UPDATE_UNINSTALL.md`](../../docs/runbooks/SORA_INSTALL_UPDATE_UNINSTALL.md).

P15.4 provides a reproducible cross-phase scenario gate for direct conversation, exact telemetry-
file analysis while dialogue remains available, an isolated coding worktree, exact editor context,
multi-monitor embodied interaction, packaged physics/recovery, local streaming voice and paired
browser reconnect. Each scenario records its command, environment, evidence links and limitations
in `docs/verification/p15-integrated-scenarios/acceptance.json`; readable logs are retained beside it.
The reference run passed all eight scenarios, including one packaged-avatar Pause action on the
actual non-primary monitor with a verified UIA postcondition. The separate primary-display raw-input
probe was intentionally recorded as not run because an unrelated full-screen application obscured
the owned fixture. See
[`docs/verification/P15_INTEGRATED_USER_SCENARIOS_GPT-5.6-Sol_2026-09-22.md`](../../docs/verification/P15_INTEGRATED_USER_SCENARIOS_GPT-5.6-Sol_2026-09-22.md).

P15.5 adds bounded avatar behavior profiles. An authorized `set_state` command can request a visual
wave, sit, lean or climb pose; a granted `move_to` command with speed at least 450 px/s uses the
running gait. These are presentation only: a climb pose does not traverse a window or prove an OS
effect. Explicit physical attention uses the existing granted `look_at` route with bounded gaze
weight and anatomical clamps. Active interaction and ragdoll pose ownership take priority over
unrelated movement, gaze and posture commands. The local player defaults to `reactive` passive
motion. Set `SORA_AVATAR_PROACTIVITY` to `quiet`, `reactive` or `ambient`, and optionally set
`SORA_AVATAR_DISTRACTION_LIMIT` to a number from `0` to `1` to scale passive motion. Quiet removes
passive idle motion; ambient adds only a small local sway, never desktop monitoring, target
selection or autonomous action. Explicit authorized states are unaffected by the passive-motion
setting. A full settings surface remains P15.7.

P15.6 adds a persistent Windows companion widget. Start Core with `--serve --api-token-file`
as above, then run the widget from this checkout:

```powershell
dotnet run --project clients/desktop_widget/desktop_widget.csproj -- `
  --token-file .local/sora-api-token
```

For a guided isolated test with the current Core, capture helper and full app, run
`.\Start-SORA.ps1` from this checkout (details in
[`SORA_LOCAL_TRYOUT.md`](../../docs/runbooks/SORA_LOCAL_TRYOUT.md)). The portable install has a stable
`bin/sora-widget.ps1` launcher. The compact window anchors to the
bottom-right of the selected monitor by default; its menu changes anchor, monitor, quiet mode and
always-on-top behavior, and closing the window hides it in the notification area. `Ctrl+L` focuses
the composer; Enter sends and Shift+Enter adds a line. Use **Delegate** for specialist work, or
expand the window to inspect recent conversation, activity, selected files and canonical reference
IDs. Code blocks use a monospaced font. Direct chat attachments now send selected local paths to
Core for a bounded read-only view; supported images can reach a configured local multimodal model,
while unknown binary formats remain a hex preview. A paste-path fallback is available if the shell
picker is slow. Task IDs
and result references are hidden until technical detail is expanded. The widget reads the owner
token from the configured private file on each request and stores no token in its preferences.
Its loopback transport, notification controls, reconnect behavior and mixed-DPI acceptance are
recorded in
[`docs/verification/P15_WIDGET_EXPANDED_CHAT_GPT-6_2026-09-23.md`](../../docs/verification/P15_WIDGET_EXPANDED_CHAT_GPT-6_2026-09-23.md).

P15.7 adds a full Windows application using the same authenticated Core state as the widget and
PWA. Run it from this checkout with:

```powershell
dotnet run --project clients/desktop_app/desktop_app.csproj -- `
  --token-file .local/sora-api-token
```

The installed launcher is `bin/sora-desktop.ps1`. Chat keeps direct conversation separate from
explicit specialist delegation. Activity exposes per-task steer/cancel with confirmation, Content
lists only Core-registered references and asks for an existing exact-scope grant before Core opens
one through its configured handler, and Integrations shows declared capabilities without enabling
or configuring extensions (P15.10). The full app's Settings page now edits the unified
`<state-root>/data/sora-settings.json`: choose a GGUF with automatic adjacent-projector discovery,
context length, GPU offload, K/V cache quantisation, flash attention and speculative/draft options.
Every row says Immediate, On model reload, or Next SORA boot. Save stages model changes;
Reload model applies them without restarting Core, with recovery to the previous working model
if loading fails. Runtime and legacy llama preferences migrate once with originals preserved.
LM Studio is optional; managed llama.cpp is served by SORA's own authenticated loopback process.
See [GUI Settings and recovery](../../docs/runbooks/SORA_SETTINGS.md) for the inventory and verified limits.
The original settings editor remains a compatibility view for older Core instances. Provider
credentials, filesystem roots and grants remain in trusted Core setup/grant workflows;
generated model credentials never enter the unified settings file. Other
§4.12 categories (reasoning-provider/routing, voice, embodiment/proactivity, privacy/storage and
extension management) are not editable here yet. The
configured-handler and full-app acceptance record is in
[`docs/verification/P15_FULL_APPLICATION_GPT-6_2026-09-23.md`](../../docs/verification/P15_FULL_APPLICATION_GPT-6_2026-09-23.md);
the settings/restart follow-up is in
[`docs/verification/P15.7_SETTINGS_RESTART_GPT-6_2026-09-23.md`](../../docs/verification/P15.7_SETTINGS_RESTART_GPT-6_2026-09-23.md).

P15.8 adds a canonical Kanban desktop window from Activity. "Fix this later (TODO)" in Chat
or on the board creates one persisted planned task **without** an agent run. The window now
opens as a small three-note board; clicking it expands TODO, IN PROGRESS and COMPLETED
sticky-note lanes. Notes are tinted by the assigned agent (Codex, Claude, Hermes,
Antigravity or SORA), with an unassigned neutral tint. Owner-local controls can add,
assign, move and remove notes. Removal only hides a note from the board; task and run
history remain. Manual placement is visibly separate from the actual run status, so
moving a planned note into COMPLETED does not claim that an agent completed it. Explicit
"Start planned" attaches the first run under the same task ID; unregistered providers
fail rather than silently substituting another specialist. A retry adds a new run without
erasing the prior one. SORA accepts exact local dialogue commands such as "Sora, add a note
for Hermes: Review the draft", "Sora, move note task-… to in progress", and "Sora, remove
note task-…". Remote dialogue does not execute board commands. Agent-native board edits
are still pending a run-bound authorized tool bridge; provider `task_updates` text is not
executed as a board mutation. No Hermes board sync or autonomous execution is enabled. See
[`docs/verification/P15_KANBAN_DESKTOP_OBJECT_GPT-6_2026-09-23.md`](../../docs/verification/P15_KANBAN_DESKTOP_OBJECT_GPT-6_2026-09-23.md).

The [owner manual-verification checklist](../../docs/verification/OWNER_MANUAL_ACCEPTANCE_CHECKLIST_2026-09-23.md)
separates physical-phone, real-device and subjective UI checks from automated stage evidence.

Local Windows voice now has shared full-app/widget press-to-talk controls and editable
Whisper/Kokoro/device preferences. See [local voice setup and acceptance](../../docs/runbooks/SORA_LOCAL_VOICE.md).
The implementation and device probes are available; full real-user audio, device-loss and
3D mouth-presentation acceptance remain open.
