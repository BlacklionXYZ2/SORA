# Docs: "wave" makes her walk on the spot; it isn't a wave

Model name: **Opus 5.5**. Checkpoint **2026-10-12 09:00:00 +01:00**, Europe/London. Status:
**documentation only**.

The owner corrected the previous entry: "Wave, as I said before, is actually walk. I have no idea
why chatgpt called it wave, but you'll notice she starts wlking when you tell her to wave."

## Correction

These entries described the "waving" pose only as one arm moving forward:
- [2026-10-12T080000 Alice default](2026-10-12T080000+0100_AVATAR-ALICE-DEFAULT_Opus-5.5.md)
  ("the wave is weak");
- [2026-10-12T084500 no wave](2026-10-12T084500+0100_OWNER-DB-TRACE-PRUNE-AND-NO-WAVE_Opus-5.5.md).

That is incomplete. In `clients/unity/Assets/Scripts/Avatar/AvatarIdlePose.cs`, the waving
profile (`PresentationProfileRegistry.cs`: `limbPulseDegrees: 24`, `limbPulseHz: 1.7`) also
swings her legs in opposite directions, ±24° at 1.7 Hz. That is the same stepping pattern as her
walk gait (±18°), so she **walks on the spot**. The live check filmed her from the front, where
the legs' forward and back swing barely shows, and only the arm was looked at.

## Changes

- **[HOW_TO_USE.md](../HOW_TO_USE.md):** "wave" is a leftover name for a walking motion; asking
  her to wave makes her walk on the spot.
- **[V1.md](../V1.md) step 5:** the note now says the same. The step itself is unchanged since
  the last entry (sit instead of wave).

## Verification

Read from the code: `AvatarIdlePose.ApplyPose` and the waving and walking values above. No new
live run.

## Limits and next

The brain is still offered "wave" as a pose (`contracts/motion.py`,
`contracts/companion_call.py`, `runtime/move_intent.py`), so "wave" still starts the walk on the
spot. Removing or renaming it is the owner's call.

HOW_TO_USE.md: updated.
