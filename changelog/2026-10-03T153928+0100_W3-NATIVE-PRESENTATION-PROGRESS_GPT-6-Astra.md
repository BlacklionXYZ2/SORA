# W3 native look / point presentation — GPT-6 Astra

Implementation/verification checkpoint completed: **2026-10-03 15:39:28 +01:00**,
Europe/London. Status: **implemented progress slice; user-side acceptance open**.
W3 and the broader frontend goal are not complete. Existing contributor changes and model
attribution were preserved; no commit, owner restart or normal-player replacement was performed.

## Changes implemented

- Added strict `look` and `point` variants to the unified `CompanionCall` union and generated
  public schemas. Each takes only a Core-issued target reference, not HWNDs, geometry, permission,
  executable code or model-authored success facts. Disabled variants are absent from the schema.
- Added focused `ControlReferences`: turn-local random reference namespace, maximum 256 entries,
  60-second expiry and selectable-only-after-exposure fencing. Only eligible native controls from
  a fresh inspection receive references; clipped/unseen, unknown, disabled, password, off-screen,
  missing-geometry and unverifiable targets cannot be selected. Existing native target registry
  owns identity, process-start, layout and topology revalidation.
- Connected `inspect_window` controls to those references and the bounded read chooser, followed
  by at most one terminal presentation. No guessed target, action repair or alternate effect is
  attempted after an invalid terminal call. Policy revocation clears reference state.
- Added an original-owner gesture-intent guard, excluding quoted/code instructions and tested
  negated, hypothetical and capability-only wording. This is a bounded guard, not a claim of
  perfect natural-language/injection resistance; real-model adversarial acceptance stays open.
- Reused static owner-local native-read/avatar policy and existing target presentation admission.
  Fresh native inspection is followed by a final policy/deadline/cancellation fence before queue
  acceptance. Remote callers do not receive these local presentation operations.
- Added deterministic Core dispatch/failure receipts and versioned trace identifiers. `look`
  dispatches gaze, not capture. `point` dispatches a real renderer interaction lifecycle, not the
  older marker-only presentation and not a desktop click/type action. Legacy explicit marker
  behavior remains unchanged.
- Registered production Unity POINT with gaze/locomotion/reach resources and no desktop semantic
  effect. Updated transport/contract validation and added a production-registration PlayMode test.
  Renderer completion is presentation-only evidence, never proof of a native application change.
- Held ambient avatar chat-state synchronization until correlated terminal feedback, disconnect
  or bounded timeout so finishing a reply does not immediately cancel a native gesture. The hold
  is established before an awaited trace write to avoid an ambient-update race.
- Allowed attached-file/image turns through the unified chooser while preserving selected-file
  and extra context. Native look/point bypasses automatic image capture and a second motion
  selector. The legacy keyword-only provider keeps its historical exclusion.
- Added 36 deterministic presentation regression cases plus a separately opt-in actual packaged
  player test, exported contracts and updated the motion runbook with current scope/examples.

## Verification

- Final `scripts/verify.ps1`, dedicated `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003`:
  **685 Python passed / 25 opt-in skipped**, **98.30 seconds**, **8 PWA passed**; Ruff, mypy
  **255 source files**, schema export check and compileall passed after the last product edit.
- C# test suite: **43 passed**; both Windows clients built with **0 warnings / 0 errors**.
- Unity PlayMode: **62 passed / 0 failed**. Rebuilt an isolated player at
  `.local/companion-target-player-20261003/SORA.exe`, not the normal installed player.
- Actual authenticated HTTP → Core target resolution → rebuilt Unity transport/lifecycle test:
  **1 passed in 7.06 seconds**, repeated on final source. Final evidence is in
  `.local/companion-point-player-qa-20261003-r4/{acceptance.json,interaction.json,player.log}`.
  Dialogue and native controls are deterministic/synthetic fixtures; renderer is an actual
  packaged procedural rig. No real LLM, native UIA fixture, custom VRM or visual acceptance.
- Final packaged command `desktop-point-800a4b3b-b613-4d9b-9671-414cf6140db5` received correlated
  renderer completion for `presentation-3b2d281d-8de4-4667-8377-dd59c74fe327` at
  **2026-10-03 14:38:07.708322 UTC**. All lifecycle records report `effect_attempted=false`;
  no desktop-action result was created. `verified=true` refers only to the presentation lifecycle.

## GUI review, cleanup and remaining work

The Computer Use skill captured the isolated full-app Chat surface in Offline test mode. Settings
input failed with `failed to activate captured window`; fresh selection and activation recovery
failed too. As the skill requires, UI input stopped. No new look/point GUI submission, Settings
editor input or visible-animation review is claimed. This recurring review limitation did not
prevent meaningful implementation and API/renderer tests.

The verified QA GUI PID 51664 was stopped; QA Core exited normally via its STOP sentinel and
port 18794 was released. Packaged test players were terminated and reaped. QA artifacts remain
for diagnosis. Owner Core `sora.exe` PID 52000, started 2026-09-29 21:49:32, remained alive and
was not reconfigured/restarted. The owner's locked environment was not mutated.

Next required work: native conversational press/type with Core-owned typed verification and
contact lifecycle; richer issued-target move/general workflows; shared user-facing lifecycle
results; real small-model/actual native app/visible custom-avatar and voice/full/compact/PWA
acceptance; prior model-editor/project/specialist and all other open alignment gates. This
checkpoint does not narrow the plan or mark the full frontend goal complete.

[Detailed evidence](../docs/verification/W3_NATIVE_PRESENTATION_GPT-6-Astra_2026-10-03.md).
