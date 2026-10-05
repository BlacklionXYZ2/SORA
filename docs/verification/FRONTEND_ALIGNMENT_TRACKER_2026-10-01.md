# SORA frontend alignment — active goal checklist

Goal: fully build the user-facing capabilities in the developed plans and verify them through the GUI. This checklist does not replace or narrow the plans. Goal remains **active** until all applicable requirements have direct evidence.

Sources: [vision alignment](../plans/VISION-ALIGNMENT_2026-10-01.md), [native perception](../plans/WINDOWS-NATIVE-PERCEPTION-AND-READ-TOOLS_2026-09-29.md), [memory/agent work](../plans/MEMORY-CHOICE-AND-AGENT-CHANGELOGS_2026-09-29.md), existing settings plan, and owner's follow-up model roster/passive-perception requirements. Learned motion research remains its separate project; existing avatar behavior and user controls are in scope.

| Requirement group | Required user-side evidence | Current goal status |
|---|---|---|
| W1 static access | GUI/JSON switches, enabled local tools without grants/approval requests, direct file authoring delegated, remote distinction, restart/recovery | In progress; first static-policy slice verified 2026-10-01 19:39:37 +01:00; [evidence and open gaps](W1_STATIC_POLICY_PROGRESS_GPT-6-Astra_2026-10-01.md); full caller/cancellation/native/GUI audit remains |
| W1 ordinary startup | One documented launch with configured helpers and correct model/avatar state | In progress; root launch/helper wiring, real model, saved settings/disable persistence and automatic compact-client sync verified 2026-10-03 08:30:46 +01:00; renderer connected/reported visible; graceful shutdown and visual/custom-avatar/full native-action acceptance remain open; [evidence](W1_W5_STARTUP_SETTINGS_GUI_GPT-6-Astra_2026-10-03.md) |
| W2 delegation and paths | Real configured project edits, agent/provider/model selection, no overlapping writers, progress/follow-up/cancel, durable path coverage and agent-authored changelog | In progress; selected-project/settings-v8/direct/isolated/read-only, atomic root reservations, bound cancellation and readable Paths/results delivered 2026-10-03 13:43:56 +01:00. Native no-inference root/junction/read-only probes and fixture cleanup passed; actual Luna edit timed out before final JSON. Successful post-fix GUI/model changelog, every adapter, full crash/alias/amendment/progress acceptance remain open; [evidence](W2_PROJECT_PATHS_GPT-6-Astra_2026-10-03.md) |
| Model/tool catalogue | Gemini 3.8 Flash via Antigravity; DeepSeek v4.1 Flash and GPT-5.6 Luna/Terra/GPT-6 Luna via Hermes; discovered full Codex roster, descriptions, actual selection, availability/errors without substitution | In progress; catalogue/per-task selector 09:19:15 plus canonical per-agent preferences, purpose/model-purpose GUI save/restart 2026-10-03 09:46:29 +01:00 verified; [latest evidence](W2_AGENT_PREFERENCES_GPT-6-Astra_2026-10-03.md); full multi-model-purpose shortlist, companion schema and live entitlement/last-success remain open |
| W4 native perception | Window list, foreground/selection/text, Desktop context, any readable local file, bounded search/read, source/freshness and meaningful unsupported results | In progress; native/read foundation delivered 2026-10-02 12:40:18 +01:00; GUI listing/file discovery and live-model API selection evidence; [remaining gates](W4_NATIVE_READ_PROGRESS_GPT-6-Astra_2026-10-02.md) |
| Passive perception | Static modes, automatic prompt context, recent non-SORA foreground, optional change-aware interval refresh, inference prioritization, pause/cancel/no stale action evidence | In progress; adaptive interval/context/foreground-priority slice 2026-10-02 23:25:49 +01:00; native/local-model timer and preemption passed; Settings GUI reviewed; [remaining full GUI/lock/cancellation gates](W4_ADAPTIVE_PERCEPTION_GPT-6-Astra_2026-10-02.md) |
| W3a semantic tools | Typed calls, target resolution, existing pose/walk/press/type from chat, independent outcome verification | Pending |
| W3b/c broad interaction | Cross-app controls, visual-only targets, bounded multi-step tasks, no replay or file-authoring bypass | Pending |
| W5 Windows voice | Actual mic/speaker, shared read/action orchestration, interruption, device loss, mouth reset | In progress; mouth relay/reset slice 2026-10-03 01:34:44 +01:00 passed packaged/speaker checks; 08:30:46 repaired settings v6 GUI recognition and reviewed compact-menu real worker Start/Ready/Close plus restart preference persistence; full spoken GUI/child-worker/real-model turn and physical loss remain open; [latest evidence](W1_W5_STARTUP_SETTINGS_GUI_GPT-6-Astra_2026-10-03.md) |
| W6a GUI truth | Shared conversation status distinct from renderer pose; actual dialogue model; readable transcripts, draft preservation, layouts and footer | In progress; first repair slice verified 2026-10-01 14:38:11 +01:00; [evidence](FRONTEND_GUI_TRUTH_GPT-6-Astra_2026-10-01.md); full DPI/race matrix open |
| W6b companion/proactivity | Avatar lifecycle/VRM/monitor/scale controls, event-driven presence, persistent settings, no unsolicited irreversible actions | Pending |
| Memory and records | Existing remember/capture/journal/changelog features exposed truthfully, persistence and inspection through usable controls where specified | Pending audit |
| Final regression/acceptance | Native, real-model, full GUI, mixed-DPI, normal restart, no owner-data pollution; detailed requirement-by-requirement final audit | Pending |

## Initial review — 2026-10-01, GPT-6 Astra

Computer Use inspection of the owner's existing full app reproduced raw Markdown and stale “Sent to SORA.” footer. Source confirmed companion projection hardcoded talking while Core is started. Existing owner session was inspected, not restarted. Rebuilt clients use isolated .local/frontend-qa-20261001 and Core port 18783 for checks; offline fixture results are not real-model capability acceptance.

Updates must record exact completion timestamps and evidence links per stage; no broad completion from a green narrow test suite.

## W2 agent preferences follow-up — 2026-10-03 09:46:29 +01:00, GPT-6 Astra

Unified v7 Settings now stores per-agent enable/purpose/preferred model/effort/model-purpose,
with preserved legacy backups. Windows GUI actual metadata dropdown, low-tier Gemini preference
Save and forced QA-Core/GUI restart persistence passed; final dropdown choices survived Save.
Fixtures verify new/board pins and active/queued per-agent revocation. Final standard gate:
603 Python passed /24 skipped, 8 PWA, 41 C#; both clients zero-warning builds. No live specialist
inference or fresh compact GUI/audio/avatar acceptance; owner Core unchanged and QA closed.
One preferred purpose per harness is not yet a full 2B-facing model-purpose catalogue. General
CompanionCall/delegation, project-root/writer-lease GUI and all broad remaining rows stay active.
[Changelog](../../changelog/2026-10-03T094629+0100_W2-AGENT-PREFERENCES_GPT-6.1-Sol.md).

## W1 follow-up — 2026-10-01 19:55:30 +01:00, GPT-6 Astra

Completed the Core delegation-revocation slice: persisted epochs, worker/resume/fallback/fan-out rechecks, pending cancellation, bounded active cancellation requests, atomic queue admission/cancel, and late-launch acknowledgement handling. Final verification: 494 passed / 13 opt-in skipped, 7 PWA and 36 C# tests. [Changelog and evidence boundaries](../../changelog/2026-10-01T195530+0100_W1-DELEGATION-REVOCATION_GPT-6-Astra.md). W1 remains in progress; real-provider process-stop/lease evidence and full GUI/native acceptance remain open. No scope rows above are removed or treated as complete by this result.

## W4 follow-up — 2026-10-02 12:40:18 +01:00, GPT-6 Astra

Implemented native text/selection/inventory and bounded local read orchestration, verified GUI
window listing and unattached file discovery with local Gemma 4 E2B, and repaired a selected-text
GUI failure with subsequent successful real-model/API verification. Full suite: 513 passed,
14 opt-in skipped, plus 7 PWA and 36 C# tests. Corrected selection/Settings GUI rechecks, native
foreground continuity, broader read/action/attachment orchestration and all other scope rows
remain open. [Changelog](../../changelog/2026-10-02T124018+0100_W4-NATIVE-READ-PROGRESS_GPT-6-Astra.md).

## W4 foreground follow-up — 2026-10-02 17:48:59 +01:00, GPT-6 Astra

Implemented native foreground continuity, revocable/health-checked transient identity and fresh
recent-window reference routing. Controlled real native/local-model selection passed; full
read/answer latency changed from 30.89s to 9.23s after disabling server-default thinking for local
companion replies. Settings-first ordering and actual model name were confirmed through the GUI.
The unnamed-window GUI read timed out before the fix; later computer-use recovery failed, so its
clean rerun remains open. Final regression: 522 passed / 16 opt-in skipped, 7 PWA checks. No other
scope row is closed. [Changelog](../../changelog/2026-10-02T174859+0100_W4-FOREGROUND-CONTEXT_GPT-6.1-Sol.md).

## W4 prompt-perception follow-up — 2026-10-02 23:00:16 +01:00, GPT-6 Astra

Implemented native-only/image-on-prompt settings, automatic metadata additions, transient validated
window images and pause. The full GUI unnamed prior-application test returned the correct `bef`
selection, closing that specific rerun gate. Actual native-image/local-model component test returned
`before` without effects. Earlier full suite: 528 passed / 16 skipped and 7 PWA checks; final targeted
and C# checks passed after status/example polish. Interval scheduling, full cancellation,
image-on-prompt GUI acceptance and all other scope rows remain open.
[Changelog](../../changelog/2026-10-02T230016+0100_W4-PROMPT-PERCEPTION_GPT-6.1-Sol.md).

## W4 adaptive follow-up — 2026-10-02 23:25:49 +01:00, GPT-6 Astra

Implemented optional adaptive interval capture, changed-image interpretation, one transient summary,
matching-context expiry, foreground model priority and bounded cancellation with late-result
rejection. Shared settings v5 adds interval/age controls and preserves v4 originals/choices.
Actual native/local-model timer and transport-preemption passed; read-only Settings review showed
all modes/timing controls and final wrapped status. Final suite: 538 passed / 18 opt-in skipped,
7 PWA checks; 36 C# tests and zero-warning builds. Full adaptive/image GUI chat, actual lock/unlock,
foreground cancellation and every other scope row remain open.
[Changelog](../../changelog/2026-10-02T232549+0100_W4-ADAPTIVE-PERCEPTION_GPT-6.1-Sol.md).

## W6 / W4 cancellation follow-up — 2026-10-02 23:52:13 +01:00, GPT-6 Astra

Implemented request-scoped owner-local Stop, admission/late-response/commit guards, local settings
and desktop invalidation, draft-preserving Windows controls and owner-mode PWA wiring. Actual
full-app and compact local-model Stop tests passed; full-app recovery replied correctly. Final
compact button sizing was reviewed after repair. Full suite: 546 passed / 18 opt-in skipped,
8 PWA tests; 37 C# tests and zero-warning builds. Voice/shared orchestration, explicit-screen
live Stop, actual lock/unlock, broader DPI/PWA acceptance and all other scope rows remain open.
[Evidence](W6_RESPONSE_CANCELLATION_GPT-6-Astra_2026-10-02.md).

## W5 shared voice follow-up — 2026-10-03 00:21:15 +01:00, GPT-6 Astra

Finalized local speech now uses the same currently implemented companion read/perception/motion
path as text, with one atomic voice receipt, shared cancellation/deadline guards and historical
spoken-time pointer samples. Playback timing and disconnect/reconnect stale-audio bugs were fixed;
the shared Windows label displays Speaking during active playback. Final regression: 562 passed /
19 opt-in skipped, 8 PWA checks, 37 C# tests and zero-warning builds. Actual local Gemma note
discovery/read passed; Whisper/Kokoro assets loaded successfully in separate component probes.
No physical mic/speaker or new live GUI voice acceptance occurred. Next: real local device/PCM
bridge, Settings and press-to-talk controls, then actual audio/GUI acceptance. No other scope row
is closed. [Changelog](../../changelog/2026-10-03T002115+0100_W5-SHARED-VOICE-ORCHESTRATION_GPT-6.1-Sol.md).

## W5 Windows bridge follow-up — 2026-10-03 01:07:47 +01:00, GPT-6 Astra

Implemented real local Whisper/Kokoro/device adapters, Core-owned worker and owner-only controls,
shared full-app/widget press-to-talk UI, v6 voice preferences with v5 backups, optional dedicated
dependency setup, child lifetime/EOF checks and startup-revocation guard. Actual adapter/hardware
and cleanup run: 13 passed; standard regression 571 passed / 23 skipped, 8 PWA and 37 C# tests;
both clients build without warnings. Full-app Start/Ready/Stop/Close and repaired voice layout
reviewed through Computer Use. Settings GUI input geometry failed; that gate remains open.
Human-spoken GUI/local-model turn, real device loss, mouth-frame transport/reset, compact GUI,
ordinary startup and broader frontend scope remain open. No full workstream is closed.
[Changelog](../../changelog/2026-10-03T010747+0100_W5-WINDOWS-VOICE-BRIDGE_GPT-6.1-Sol.md).

## W5 mouth follow-up — 2026-10-03 01:34:44 +01:00, GPT-6 Astra

Implemented private worker-derived PCM presentation relay, bounded output-only renderer metadata,
VRM expression application, stale/reconnect/overflow reset and mouth watchdog. Fixed repeated
close and native speaker-write/close lifetime race found by interruption testing. Packaged sample
VRM plus actual speaker tests passed twice after repair, including actual zero expression weights
for completion/interruption/simulated device loss/disconnect. Final suite: 575 passed / 24 skipped,
8 PWA, 40 C# and 61 Unity tests; zero-warning Windows client builds and rebuilt player.
The final transcript is synthetic and dialogue offline; pipe sink is forwarded in-process by the
test. Full real-user GUI/child-worker/real-model voice, physical device loss, normal launch and
other workstreams remain open. No broad scope closure from these component/integration results.
[Changelog](../../changelog/2026-10-03T013444+0100_W5-VOICE-MOUTH-INTEGRATION_GPT-6.1-Sol.md).

## W1 / W5 GUI/startup follow-up — 2026-10-03 08:30:46 +01:00, GPT-6 Astra

Root startup now wires press/type as well as observation/capture. Computer Use caught and repaired
settings-v6 rejection that hid unified GUI controls; added section navigation and accurate audio
close reason. Actual root-managed Gemma/explicit projector, automatic compact-client launch,
real-model full-app answer, restored transcript, GUI Voice preference save and restart persistence
passed. Compact Voice reached Ready with real child worker and closed/reaped it without recording.
Final regression: 576 passed /24 skipped, 8 PWA, 40 C#; zero-warning builds and launcher parses.
Renderer connected/reported visible with actual topology, but transparent window not exposed by CU.
Owned QA restarts were forced, not graceful; all QA trees closed, owner Core unchanged. Human-spoken
voice/physical device, broad action/catalogue/delegation, mixed-DPI and other rows remain open.
[Changelog](../../changelog/2026-10-03T083046+0100_W1-W5-STARTUP-SETTINGS-GUI_GPT-6.1-Sol.md).

## W2 project/path follow-up — 2026-10-03 13:43:56 +01:00, GPT-6 Astra

Canonical v8 project/mode/base-ref and GUI specialist deadline, pinned task destinations, direct
Codex boundary, atomic roots, owned writer-tree stop and conservative reconciliation, labelled
Paths metadata and readable result UI implemented. Actual native command checks passed inside/
outside/read/junction/read-only cases without inference. Full GUI Paths/result/draft controls
reviewed and layout repaired. A real Luna/low edit changed the fixture but timed out under the old
30-second Core deadline; final JSON/changelog completion was not verified. Deadline now defaults
to 300 in canonical settings; second model launch was policy-blocked, not rerouted. Final suite:
608 Python passed /24 skipped, 8 PWA, 41 C# and zero-warning clients. Owner Core untouched, QA closed.
Full successful post-fix GUI/model work, every adapter boundary, crash/alias/amendment matrix,
multi-model shortlist/CompanionCall, compact/PWA acceptance and every other unfinished row remain
active. No broad stage or goal closed. [Evidence](W2_PROJECT_PATHS_GPT-6-Astra_2026-10-03.md).

## W3 companion-call follow-up — 2026-10-03 14:21:58 +01:00, GPT-6 Astra

Added unified strict/local enabled read/list/delegate/pose/pointer-move vocabulary and bounded
chooser, cached paged known model/project references, original-owner atomic task admission,
separate inspectable suggested brief, no automatic prior-desktop-history delegation, queued
receipts, versioned traces and shared readable request/brief evidence. Repaired module-authoring
classification/fast-path boundary bypass and passive-image-vs-motion/second-selector bugs.
Final standard suite: 634 Python passed /24 opt-in skipped, 8 PWA, 41 C#; zero-warning clients.
Computer Use captured initial isolated Offline test GUI, but activation and recovery failed before
draft entry. No new GUI submission/result or real small-model acceptance claimed. QA closed,
owner Core unchanged. Editable multi-model purposes, native action executors/verifiers, live and
voice/compact/PWA acceptance and all other plan gates remain open. No workstream or goal closed.
[Evidence](W3_COMPANION_CALLS_GPT-6-Astra_2026-10-03.md).

## W2/W3 multi-model purposes — 2026-10-03 14:53:12 +01:00, GPT-6 Astra

Implemented canonical v9 per-agent model-purpose lists, original-preserving migration, strict
bounds/recovery and monotonic hand-edit revisions; live cached catalogue overlays and configured/
listed provenance; filtered paged companion discovery; shared Settings/catalogue draft editor
with atomic save/error retention and v9 client parsing. Actual controlled HTTP save→discover→
delegate exact-model flow passed without inference. Final suite: 649 Python passed /24 skipped,
8 PWA, 43 C#; zero-warning clients. Computer Use activation/recovery failed before Settings entry;
new editor render/input/save/restart/full/compact and real local-model acceptance remain open.
QA closed, owner untouched. Shortlist code is implemented, not user-side verified; all broader
workstreams/remaining rows stay active. [Evidence](W2_W3_MODEL_PURPOSES_GPT-6-Astra_2026-10-03.md).

## W3 native look/point — 2026-10-03 15:39:28 +01:00, GPT-6 Astra

Implemented strict opaque eligible-control references, bounded actual-context exposure/expiry,
native revalidation and static/cancellation fences, original-owner gesture intent, truthful
receipts, production POINT presentation-only lifecycle and ambient hold. Preserved attached-file
context/unified chooser; no native press/type added. Final suite: 685 Python passed /25 skipped,
8 PWA, 43 C#, 62 Unity; zero-warning clients. Actual isolated rebuilt player completed the
authenticated Core POINT flow with deterministic dialogue/synthetic controls, no desktop effect.
Computer Use failed activation/recovery before entry; new visual/GUI/real-model/native-application/
custom-avatar acceptance remains open. QA closed, owner unchanged, normal player not replaced.
Native press/type typed verifiers, general target/move workflows, frontend lifecycle and all other
unfinished rows remain required. [Evidence](W3_NATIVE_PRESENTATION_GPT-6-Astra_2026-10-03.md).

