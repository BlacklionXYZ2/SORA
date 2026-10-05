# P12.3 ragdoll and recovery — GPT-5.6 Sol

Status: **complete 2026-09-17 11:33:37 +01:00**.

P12.3 adds a deliberately bounded screen-plane ragdoll and get-up path to the licensed VRM. It is a deterministic joint-constraint controller, not an unconstrained PhysX Rigidbody puppet: that choice makes ownership, limits, recovery and timeout behavior reproducible while retaining the existing body capsule and P12.2 monitor-support collision model. P12.4 still owns selected window surfaces and P12.5 owns semantic fall/land feedback.

## Implementation

- `AvatarRagdollRecoveryController` owns falling, settling and recovering states over 12 hips/spine/chest/head/arm/leg transforms. Every target rotation is clamped by a finite anatomical angular limit and approached at a bounded angular rate.
- A body-up classifier distinguishes upright, front, back, left-side and right-side poses. Recovery begins only after the pose remains within 0.75 degrees of its constrained target for 220 ms.
- Get-up blends from the captured settled pose to the exact imported rest rotations over 650 ms. A three-second global timeout restores every registered joint exactly, clears the state and releases ownership.
- `AvatarPoseOwnership` provides one full-body presentation lease. Idle limbs, gaze/head tracking, semantic torso presentation and procedural reach/IK all skip writes while recovery owns the pose. Starting recovery aborts an active reach and clears gaze; native capture, grab and simple falling also stand down.
- P12.2 publishes an internal landing impulse. Downward impact at or above 1000 physical px/s enters recovery; horizontal impact at or above 350 px/s selects the appropriate side, otherwise the bounded default is a front fall. This is local presentation integration only, not the semantic event stream deferred to P12.5.
- The existing root `CapsuleCollider` remains the bounded avatar collision envelope. P12.3 does not create desktop geometry per limb or window; P12.4 will add selected support surfaces.
- An explicit `SORA_RAGDOLL_EVIDENCE_PATH` acceptance hook runs only when requested by the packaged test. It cycles all four fall planes and writes no credentials or desktop content.

## Controller-contention acceptance

PlayMode starts a reachable procedural arm action, then starts recovery. Recovery aborts and restores that action, acquires `ragdoll-recovery`, rejects a second reach and preserves its owned pose while presentation, gaze and IK are deliberately invoked. Interrupt, successful recovery and forced timeout each restore the exact hips rest rotation and leave no pose owner.

The impact fixture rejects a 999 px/s landing, classifies positive and negative horizontal hard impacts as right/left side, and classifies a hard vertical impact as front. Invalid body-up vectors are treated as upright rather than propagating NaN/Infinity.

## Bundled and packaged VRM acceptance

The Unity suite loads the actual bundled Seed-san VRM through the standalone UniVRM runtime and executes front, back, left-side and right-side recovery using at least 11 constrained humanoid joints. The production packaged player reported 12 constrained joints, an enabled body collision capsule and these results:

| Requested | Detected | Outcome | Elapsed |
|---|---|---|---:|
| Front | Front | Recovered | 1.2167 s |
| Back | Back | Recovered | 1.2170 s |
| LeftSide | LeftSide | Recovered | 1.2167 s |
| RightSide | RightSide | Recovered | 1.2169 s |

The pose lease was released after the sequence. The same 83.60-second packaged run retained native blank/avatar input routing, the real 160-pixel P12.2 drop, Core position reporting, 28 runtime-tuned SpringBone joints on every launch, graceful shutdown and reconnect without movement replay. The actual display topology was observed but not changed.

## Verification

| Gate | Result |
|---|---|
| Unity 6000.6.0f1 PlayMode | 38/38 passed; P12.3 fixtures 9/9 |
| Unity Windows build | Passed; managed embodiment SHA-256 `85A6AC33740FFE4BC3D5099DA2CFD3E9336E481884310EEADC3E8B64A17A3160` |
| Packaged Core/player/native input | 1/1 passed in 83.60 seconds |
| Portable C# / embodiment | 22/22 C#; 35 passed, 3 explicit opt-in skips |
| Codex provider regression | 6/6 after start/cancel race repair |
| Repository | 273 passed, 9 explicit opt-in skips |
| Static/contracts | Ruff passed; official locked strict mypy passed across 147 source files; schemas and compileall passed |

Machine-readable evidence is in [`p12-ragdoll-recovery/acceptance.json`](p12-ragdoll-recovery/acceptance.json). Raw player logs and transient runtime artifacts remain under ignored `.local/p09-unity-evidence`.

## Boundary and next stage

This stage does not claim free 3D rigidbody simulation, limb-level desktop collision, bounce, selected window supports, occlusion handling or Core-visible physics events. P12.4 is next: it will add bounded taskbar/window-top support lifetimes and predictable removal/minimize/move behavior without constructing geometry for every UI element.
