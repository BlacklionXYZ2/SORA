# Physics body in SORA: she could get stuck and unable to move

Model name: **Opus 5.5**. Checkpoint **2026-10-17 17:15:00 +01:00**, Europe/London. Status:
**fixed and relaunched; the original stuck state was not reproduced**.

The owner: "SORA's stuck and cannot move whether she tells her avatar to or I try to physically
move her."

## Cause

During a fall her body holds her pose (`physics fall`). That makes SORA ignore movement commands
(`presentation.IsPoseOwned`), and grabbing waits until the fall is over. Two ways a fall could
never end:
- **Waiting for an impact that never comes:** settling waited for some part other than her feet
  to touch a surface. If she stayed on her feet (caught herself after a landing), it waited
  forever.
- **Falls her body started itself** (a stumble or a tip): SORA wasn't told, so it kept animating
  and moving her mid-fall.

The stuck session's avatar log can't confirm which happened: the player writes nothing after
loading.

## Changes

**`FallController`** (motion-lab, synced to SORA):
- if she comes to rest with only her feet ever touching down, she caught herself, and the fall
  ends;
- **no fall lasts longer than 12 s.**

**`AvatarPhysicsBody`:**
- a fall her body starts itself puts SORA into falling mode too, and gives her back when she's up;
- every state change is logged: held, let go, hard landing, fell by herself, standing again (with
  the fall's events), resynced.

**`P18PhysicsBodyTests`:** a new test, `EveryFallEndsAndGivesHerBack`, covers a hard landing
straight down and a hard shove. The shove didn't topple her: the balance helper held her.

## Verification

- P18: 6 of 6 pass. The rest of SORA's suite was unaffected by these files (84 of 84 passed
  earlier today, with the previous P18 set).
- Rebuilt and relaunched in the owner's profile (SORA's processes ended as before). The avatar
  process is responding and busy, at about 0.7 of a CPU core.
- **Live, through Core's API:** a `move_to` 471 px left at 300 px/s was queued and she arrived
  within 2 s (Core reports x 2600). A screenshot shows her standing upright there.
- **Not run live:** dragging her by hand, and a hard drop. The owner is reviewing.

Nothing committed.
