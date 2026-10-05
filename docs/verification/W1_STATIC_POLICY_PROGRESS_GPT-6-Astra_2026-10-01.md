# W1 static access — implementation progress

Contributor: GPT-6 Astra. First implementation slice finished **2026-10-01 19:39:37 +01:00 (Europe/London)**. Workstream status: **in progress**, not accepted as complete.

## Implemented

- Unified settings schema 3 adds eight Companion access switches. Schema-driven desktop settings receives their labels, boolean controls, live effect tier and explanations; no second settings store. Direct user-file writing defaults OFF and explicitly says no direct writer is installed.
- Version 2 migration preserves model/preferences/revision and any explicit access disables, saves the original bytes in a uniquely named v2 backup, and writes version 3. Version 3 missing access fields is invalid, not a first migration. Strict booleans reject ambiguous string values.
- A separate settings recovery copy is updated on valid saves/refreshes. Invalid startup settings recover a readable prior configuration or disable all companion access. Invalid originals remain intact until explicit repair. Model recovery remains separate.
- Owner HTTP and embodiment WebSocket paths enter a server-established local context only after owner bearer authentication. Remote routes do not enter it; a caller-controlled device ID does not establish local origin.
- LocalPolicyContext carries request scope, effect names, settings revision and policy epoch, with no grant/approval fields or use counter. Explicit effects cover desktop observation/capture, reads/writes, interaction/navigation, avatar and voice. Unknown tool.invoke resources are not a wildcard.
- Runtime authorization consumption and pre-delivery checks distinguish local policy from persisted grants. Policy changes invalidate previously prepared local work, even if a switch is turned back on, and clear volatile targets, references, captures, attention and voice session state. Active desktop subscriptions lose authority immediately and schedule native shutdown.
- Settings-backed dialogue capture and managed avatar startup/dispatch do not mint or consume grants. The avatar monitor checks the static switch. Legacy embedded runtimes without AppSettingsController still have their old grant paths; these are not the final architecture.
- File attachments honor the read switch. Dialogue selection respects avatar/capture switches, and a reply is discarded if access settings change during generation. Task submit/start/retry/steer admission checks delegation settings.
- Content navigation no longer asks for a grant ID in the full app; it posts through the normal authenticated API and still requires a real reference and configured handler. Target identity/topology checks remain.
- Exported app-settings and settings-edit schemas updated; desktop projections accept versions 2 and 3, and the settings editor posts the version received from Core.

## Verification

- Full scripts/verify.ps1: **477 passed, 13 opt-in skipped**, 73.59 seconds; Ruff, mypy, schema freshness, compileall and **7 PWA tests** passed. This run preceded the final nine additional regression cases, which were run separately below; it is not a claim of one 486-test full run.
- Final targeted policy / local avatar / file-and-capture dialogue set: **30 passed**, 2.50 seconds. Includes settings migration/recovery, strict booleans, authenticated HTTP with no grant header, OFF denial despite forged grant header, device-name spoof rejection, OFF→ON stale authority, each registered effect OFF, capture and avatar no-mint/no-consume spies.
- Final Ruff, mypy (**216 files**) and schema freshness checks passed after the added tests.
- C# tests: **36 passed**. Full application build: zero warnings/errors, isolated output .local/policy-qa-20261001/desktop.
- Scoped git diff whitespace check passed (normal LF/CRLF notices).

## User-side review boundary

Computer Use selected the isolated rebuilt full app and read its Chat accessibility tree: Ready to talk, Offline test model, Attach file, Send, Look, Delegate, TODO, Content, Settings and 3D companion controls were exposed. No real model was invoked.

The screenshot showed the foreground game rather than the target app. Clicking Settings was rejected because the game covered the input point. Activation then reported user input. No further UI input was sent. **Companion access layout, Content layout and switch interaction are not visually accepted.** The Computer Use skill also prohibits changing in-app security/privacy settings; enforcement was tested through isolated code/API fixtures, not by clicking access switches or altering owner settings.

Owned QA Core and full-app processes were stopped after verifying their exact IDs and QA command lines. Owner Core, model server, game and other apps were not stopped or restarted. QA data/logs remain under .local/policy-qa-20261001. The running everyday SORA instance has not been upgraded in place.

## Remaining W1 work — do not close the gate yet

**Follow-up completed 2026-10-01 19:55:30 +01:00:** persisted delegation epochs, queued/restart/resume/fallback/fan-out launch guards, bounded active cancellation requests, atomic cancellation/admission and late-acknowledgement handling are implemented and regression-tested. See the [GPT-6 Astra follow-up changelog](../../changelog/2026-10-01T195530+0100_W1-DELEGATION-REVOCATION_GPT-6-Astra.md). Final full gate now passes 494 tests with 13 opt-in skips, plus 7 PWA and 36 C# tests. This advances item 3 below but does not establish real-provider process-stop or voice cancellation acceptance.

1. Remove the legacy no-AppSettingsController auto-grant paths once all embedded/test/internal callers have a real static settings source. Preserve historical records and remote grant semantics.
2. Audit every API, internal/background and streaming entry point. Existing extension/workspace integration tool.invoke resources still need explicit registered effects; they currently do not gain a blanket local bypass. Some routes still use historical authorization-error wording.
3. Complete cancellation/recheck semantics for queued and running specialist work, all fan-out/fallback/resume paths, and in-flight voice delivery. Admission checks alone are not full cancellation evidence.
4. Test actual settings-backed HTTP/WebSocket/native helpers together, including negative and reconnect paths, disabled-at-start avatar behaviour and re-enabling/restarting the renderer. The current fixture tests do not prove packaged Unity behaviour.
5. Audit corruption/recovery fault ordering and interrupted writes, including stale recovery snapshots and simultaneous disk edits. Preserve explicit disables; never infer default enablement from corrupt state.
6. Consolidate ordinary startup and GUI controls (W1b), inspect final settings/content layouts and DPI behaviour when the desktop is available, and test restart with the user's normal runtime without changing their preferences unexpectedly.
7. Continue W4 native context, W2 direct project delegation/catalogue, W3 action schema, passive perception, W5 voice, W6 lifecycle/proactivity and the full acceptance tracker. No full companion-completion claim follows from this slice.
