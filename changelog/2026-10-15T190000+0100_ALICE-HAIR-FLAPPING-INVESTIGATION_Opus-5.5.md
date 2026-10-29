# Alice's hair tips flapping: colliders made gentler, and hair settling measured

Model name: **Opus 5.5**. Checkpoint **2026-10-15 19:00:00 +01:00**, Europe/London. Status:
**changes made; the owner's report not reproduced on the current build**.

The owner: "Her hair bones get really funky on the end and flap around violently constantly."

## Findings

- **Duplicated joints aren't the cause.** Her file puts 128 of its 178 simulated bones in
  more than one spring group, but UniVRM's VRM 0.x conversion already drops those duplicates
  (the "duplicated spring joint" warnings in her player log). A guard that removes duplicates
  was added anyway, and it removes nothing for Alice. Switching it off changed no test result.
- **Her file's springs are unstable at very short frames.** Measured at SORA's scale (0.6
  units tall) with her standing still for 2 s, as the fastest tip's movement per frame (at life
  size):

  | Setup | 60 fps (SORA's rate) | Uncapped (about 1 ms frames) |
  |---|---|---|
  | Her file as-is | 0.1 mm | **6.4 mm** |
  | Tuned, without generated colliders | 0.0 mm | 0.1 mm |
  | Tuned | 0.0 to 0.1 mm | 0.3 mm |

  The tuning calms her file at short frames. SORA's player runs at 60 fps.
- **The generated colliders shoved hair in some cases.** At full size with uncapped frames,
  a hair tip with the earlier collider rules moved 8.4 mm a frame.
- **Real player, isolated profile, her idling:** frame-to-frame image change around her
  body was 0.02 to 0.1 out of 765, so nothing visibly flapping. Her blonde hair against a
  white window behind her makes this a weak visual check.

## Changes (`clients/unity`)

- **`AvatarSecondaryParts.cs`:**
  - hair no longer collides with her arms, because her posed arms move inside long hair;
  - a chain gets no collider group if **any** of its bones (not just the first two) is inside
    one of the group's capsules in her rest pose;
  - the duplicate-joint guard;
  - `generateColliders` can be switched off.
- **`SoraBootstrap.cs`:** `SORA_SECONDARY_COLLIDERS=0` turns the generated colliders off, as a
  diagnostic switch.
- **`P16SecondaryPartsTests.cs`:**
  - new: a settling measurement at SORA's scale and frame rate, plus uncapped, for three setups;
  - Alice must settle at 60 fps (no tip faster than 2 mm a frame);
  - each bone is simulated by one spring;
  - chains clear of her body get colliders (144 of 146 springs).

## Verification

- Unity PlayMode: 69 passed / 0 failed; the player was rebuilt in place.
- Live: the isolated idle check above.
- **Not reproduced:** the flapping the owner saw. They may have been running an earlier build:
  the change from the 17:30 entry, before the arm and rest-overlap collider rules, or the
  pre-existing player.

HOW_TO_USE.md: no change to usage.
