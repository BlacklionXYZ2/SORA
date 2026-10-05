# P11.1 animation, IK and semantic-presentation verification

Completed: **2026-09-15 11:14:26 +01:00**  
Model: **GPT-5.6 Sol**  
Status: **complete**

## Acceptance outcome

P11.1 satisfies its implementation-plan acceptance criteria. The Unity embodiment now has a
data-driven semantic presentation-profile registry and a procedural two-bone reach layer. Inside,
outside, left, right and interrupted fixtures return the controller to a valid state, and adding a
`THINKING` presentation is a profile registration/configuration change rather than a branch in Core
or an interaction controller.

This stage is presentation only. It does not implement P11.2's shared semantic-action lifecycle,
P11.3's authorized Level 3 side effect, or claim that an animation authorizes or proves an OS effect.

## Implemented behavior

### Semantic presentation profiles

- Extended the Core contract with semantic states `thinking`, `listening`, `speaking`,
  `waiting_for_agent`, `reading` and `typing`, while retaining `idle` and the derived `moving` and
  `looking` states.
- Prevented callers from directly setting derived movement/gaze states.
- Added optional validated presentation styles and presentation-facing action kinds for `point`,
  `press`, `type` and `place_object`. These fields contain no grant or outcome evidence.
- Added a Unity `PresentationProfileRegistry` that independently maps state/action plus optional
  style to replaceable visual parameters: blend/retraction timing, gaze weighting, reach scale, arm
  preference, torso lean/tilt and bounded procedural pulse.
- Added `AvatarPresentationController`, which applies profile data to a humanoid torso bone without
  switching on semantic state names. Unknown states fail closed; an unknown style falls back to the
  registered default profile for that same semantic name.
- Registered `THINKING` as data and proved that adding it to a registry makes the existing generic
  presentation controller render its configured pose without changing that controller.

### Procedural reach and gaze layer

- Added `AvatarReachController`, executed after the existing idle pose and gaze layers.
- Binds to the humanoid left/right upper arm, lower arm and hand/fingertip bones.
- Selects the nearest reachable arm unless a profile requests a reachable left/right preference.
- Computes reachability from the live bone-chain lengths and a bounded profile reach scale.
- Uses deterministic two-bone geometry, weighted fingertip orientation, and profile-controlled
  blend-in/retraction instead of inference in the frame loop.
- Gives the reach presentation temporary weighted gaze/aim toward the target.
- Preserves and restores the selected arm's pre-reach local rotations on completion, interruption,
  replacement, component disable, and failed/out-of-reach attempts.
- Reports presentation-only outcomes (`Presented`, `OutOfReach`, `Interrupted`) and never represents
  them as proof of contact or a semantic effect.

### Runtime and transport integration

- Configures the torso presentation and reach components only after the runtime VRM has been
  validated as humanoid.
- Applies validated `set_state` profiles and optional action-presentation profiles in the Unity
  command consumer.
- Reports semantic state when locomotion/gaze are inactive; active movement and gaze remain derived.
- Resets presentation state on disconnect/topology suspension.
- The C# transport allowlists semantic states/actions/phases and validates identifier-shaped style
  names before a command reaches Unity's main thread.

## Verification evidence

### Unity 6.6 PlayMode

```text
.\scripts\build-embodiment.ps1 -TestOnly
Result: Passed
Total: 7
Passed: 7
Failed: 0
Skipped: 0
```

The three new P11 fixtures passed:

- `ThinkingAndStylesAreRegistryDataNotControllerBranches`
- `ReachChoosesLeftAndRightArmsAndRetractsToIdle`
- `OutsideReachAndInterruptedReachEndInValidIdleState`

The four prior P09 presentation/coordinate/VRM fixtures also remained green. Unity reported no C#
compilation, activation, or native-allocation leak failure.

### Repository and portable embodiment gates

```text
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

The four ordinary repository skips remain the explicitly opt-in UIA privilege/native transport and
packaged Unity checks. The packaged Unity player was not rebuilt for P11.1; the Unity editor compiled
the actual project and executed all seven PlayMode tests. Packaging and a recorded physical Level 3
demo belong to later P11 acceptance.

## Boundaries and next stage

- The presentation registry is deliberately small. It does not establish the final animation-clip
  asset system or freeze a future Unity hierarchy.
- The reach layer owns visual bones only. It does not invoke UIA, synthesize input, consume grants,
  or claim contact.
- P11.2 must add the generic registered-action lifecycle and controller arbitration without adding
  action-specific branches to the generic executor.
- P11.3 must recheck exact target/grant authority at contact and independently verify the semantic
  effect.
