# P15.5 advanced avatar behavior — GPT-6

Completed: **2026-09-22 21:38:50 +01:00 (Europe/London)**.

## Scope and authority

- Four new semantic presentation states (`waving`, `sitting`, `leaning`, `climbing`)
  are validated by Core and the C# transport. They remain presentation-only; they
  are not desktop action verbs, physical surface traversal, or effect evidence.
- Core's `embodiment.command` exact-scope grant remains required before a state
  is queued. Unity receives the authorized command, not grant material. A
  missing-grant test rejects the new wave state; the same state is delivered
  with the persisted exact-scope grant.
- A granted `move_to` at 450 px/s or faster selects a stronger running gait.
  Movement, gaze and state commands cannot interrupt an active registered
  interaction or exclusive ragdoll pose owner. Procedural reach retains arm
  priority; limb poses leave owned bones alone.
- Existing physical screen-point attention is weightable and anatomically
  clamped. An idle explicit look keeps full weight; a non-idle semantic profile
  can provide gentler gaze. It does not move the avatar or authorize an OS effect.
- `SORA_AVATAR_PROACTIVITY=quiet|reactive|ambient` selects only local passive
  idle motion; `SORA_AVATAR_DISTRACTION_LIMIT=0..1` scales it. Default is
  `reactive`. Quiet removes passive idle sway. Ambient raises that small sway
  but never selects targets, observes the desktop, starts inference or acts.
  Explicit Core-authorized gestures are not silently disabled by this local
  passive-motion preference. Invalid settings fail configuration.

## Verification on the Windows development machine

| Command/check | Result |
|---|---|
| `uv run --locked pytest tests/embodiment/test_presentation_contract.py -q` | 2 passed |
| `dotnet test clients/csharp_tests --verbosity quiet` | 22 passed |
| `uv run --locked python scripts/export-contracts.py` | regenerated state and command schemas |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1` | 346 passed, 10 explicit opt-in native/Unity skips; Ruff, strict mypy across 186 source files, schema check, compileall, browser 7/7 passed |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-embodiment.ps1 -TestOnly` | Unity 6000.6.0f1 PlayMode 59/59, including four new P15.5 cases; `.local/p09-unity-evidence/playmode-results.xml` |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-embodiment.ps1 -SkipTests` | Windows player build succeeded; `.local/p09-unity-evidence/build.log` reports `PlayerBuildInfo success:true` |

The first repository gate correctly refused stale generated schemas after the
new enum members. They were regenerated and the full gate then passed. The
first two Unity runs preceded a final test/arbiter refinement; the recorded
59/59 report is newer than all final Unity source and test files.

## Limits and next gates

The PlayMode fixtures use a deterministic humanoid-bone proxy and direct gaze
math; they do not assess subjective animation quality on the packaged VRM.
Sitting and climbing are visual poses, not contact with a verified seat or a
surface-climb controller. No new autonomous desktop reaction is enabled by
ambient mode. P15.7 will expose these controls in the shared settings UI.
P15.2 still requires an independently verified physical paired phone and
trusted certificate; this work does not close that gate. No commit, tag or
staging operation was performed.
