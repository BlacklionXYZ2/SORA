# P11.2 action registry and interaction-lifecycle verification

Completed: **2026-09-15 13:21:17 +01:00**  
Model: **GPT-5.6 Sol**  
Status: **complete**

## Acceptance outcome

P11.2 satisfies its implementation-plan acceptance criteria. Unity now has a small
`EmbodimentActionRegistry`, independently registered action components, atomic presentation-controller
ownership, and one deterministic controller that drives every action through:

```text
Navigate → Align → Reach → Contact → SemanticEffect → Verify → Retract
```

Fixture POINT and PRESS actions use the same controller instance and phase machine. The generic
controller contains switches only for lifecycle phases; it contains no POINT, PRESS, TYPE or other
action-name branch. A newly registered fixture action runs without modifying that controller.

This stage does not implement P11.3's real Level 3 action. The semantic effects exercised here are
deterministic in-process fixtures. No UIA invocation, synthesized input, media mutation or other OS
side effect was added or claimed.

## Components

### `EmbodimentActionRegistry`

- Registers independently supplied `IEmbodimentActionComponent` instances by normalized action ID.
- Rejects duplicate registrations and unknown action resolution.
- Registration carries no authority and cannot create a capability grant.
- `DelegateEmbodimentAction` keeps per-action effect, effect polling, verification and cleanup outside
  the generic controller.
- Effect start and effect polling are separate callbacks, preventing a pending effect from being
  started repeatedly on successive frames.

### `EmbodimentInteractionController`

- Uses one lifecycle-phase state machine for all registered actions.
- Checks connection, deadline and target validity before every pre-retraction phase.
- Starts the semantic effect at most once, polls it separately, and runs independent verification.
- Converts interruption after an attempted but unverified effect into explicit `UnknownOutcome`.
- Attempts retraction for cancellation, timeout, target loss and ordinary phase failure.
- Performs immediate safe cleanup when disconnected presentation cannot be retracted normally.
- Releases controller ownership even when environment or action cleanup throws.
- Does not roll back a verified semantic outcome merely because presentation cleanup fails; it reports
  `completed:cleanup_failed` while still releasing presentation resources.

### `PresentationOwnershipArbiter`

- Atomically claims an action component's declared locomotion, gaze, reach or future controller set.
- Rejects a competing action without partially acquiring a subset of claims.
- Releases all claims on completed, cancelled, failed, unknown, disconnect and cleanup-exception paths.

### `AvatarInteractionEnvironment`

- Adapts the generic lifecycle to P11.1's gaze, semantic-profile and procedural-reach components.
- Keeps the already validated P10 world target as the navigation input.
- Aligns gaze, begins the registered action's presentation profile, waits for reach/hold, confirms the
  visual contact condition, and retracts through the same environment interface.
- On disconnect or cleanup, immediately restores reach/gaze/presentation to a valid idle state.
- Exposes no semantic OS-effect implementation; P11.3 must supply that through an authorized action
  component rather than through the presentation environment.

## Adversarial acceptance

Unity PlayMode fixtures verify:

- POINT and PRESS traverse the same controller and exact phase sequence.
- Both independently registered effects execute once and verify once.
- A newly registered `wave` fixture action uses the same controller without action-specific changes.
- A competing simultaneous controller grab receives `controllers_busy` and acquires no partial
  ownership; it may start after the first interaction cleans up.
- Cancellation before effect returns `Cancelled` and executes no effect.
- Timeout before effect returns `Failed` and executes no effect.
- Target loss before effect returns `Failed` and executes no effect.
- Disconnect before effect returns `Failed`, executes no effect and releases all ownership immediately.
- Disconnect during retraction preserves an already verified semantic outcome, ends the controller
  immediately and releases all ownership rather than waiting for unavailable presentation.
- A pending effect is begun once and polled separately; cancellation afterward returns
  `UnknownOutcome` without blind repetition.
- Environment and action cleanup exceptions cannot leak ownership or invalidate an independently
  verified outcome.

## Verification evidence

```text
.\scripts\build-embodiment.ps1 -TestOnly
Unity 6.6 PlayMode: 12 passed, 0 failed, 0 skipped

.\scripts\verify.ps1
Ruff: passed
strict mypy: passed across 140 source files
schema freshness: passed
pytest: 249 passed, 4 explicit opt-in skips

.\scripts\verify-embodiment.ps1
.NET build: passed, 0 warnings, 0 errors
C# transport/coordinate tests: 22 passed
Python embodiment suite with real C# transport: 35 passed, 1 packaged-player skip
```

The twelve Unity tests comprise the original four P09 tests, three P11.1 presentation/reach tests,
and five P11.2 registry/lifecycle tests. Unity reported no C# compilation, activation or native
allocation leak failure. `git diff --check` reported no whitespace error; its output contained only
the repository's existing line-ending normalization notices.

## Boundaries and next stage

- The fixture semantic effects establish lifecycle extension and verification behavior, not an OS
  action or permission model.
- P11.3 must bind one registered component to an exact persisted Level 3 grant, recheck target and
  authority at contact, prevent blind repeat after a crash/uncertain result, and independently verify
  the real effect.
- P11.4's deterministic media Pause demonstration and P11.5's logical typing remain open.
- The packaged Unity player was not rebuilt in this stage. Unity compiled the actual project and ran
  its complete PlayMode suite.
