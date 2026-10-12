# The "wave" pose is gone; asking her to walk means the real walk

Model name: **Opus 5.5**. Checkpoint **2026-10-12 09:12:00 +01:00**, Europe/London. Status:
**implemented**. The Python side is verified. The Unity PlayMode tests and avatar rebuild have
**not** run yet.

The owner answered the open question in the
[previous entry](2026-10-12T090000+0100_WAVE-IS-A-WALK-DOCS_Opus-5.5.md): "Yes, change wave to
walk." Moves V1 step 5 (move and indicate) forward.

The code change was made at about 08:53 by the Opus 5.5 session working on the owner's machine.
That session hit its usage limit before it could test the change or write this entry. A second
Opus 5.5 session wrote this entry from that session's transcript and the pushed repository
(commit `78ab9b9`), and ran the checks below.

## Changes

- **Brain contracts:** `wave` is removed from `MotionKeyword` (`src/sora/contracts/motion.py`)
  and from the companion call's `PoseName` (`src/sora/contracts/companion_call.py`). The model is
  now offered sit, lean, climb, stand and walk only, and its prompt says she has no wave or other
  gesture.
- **Avatar contract:** the `waving` presentation state is gone from
  `EmbodimentPresentationState`. The JSON schemas in `contracts/schema/v1/` were re-exported.
- **Runtime, avatar and old app:** the move intent, read turn, local player, Unity presentation
  profile and the frozen full app no longer send or handle a wave.
- **Decision layer:** the motion family's description now reads "walking, running, sitting".
- **Tests and training labels:** wave cases were rewritten as sit or walk. Seed messages that
  mention a wave in the owner's words are kept as natural-language inputs.
- **Docs:** [HOW_TO_USE.md](../HOW_TO_USE.md), [V1.md](../V1.md) step 5 and
  [the motion keyword runbook](../docs/runbooks/SORA_MOTION_KEYWORDS.md) say she has no wave and
  to ask her to walk instead. Older plans and records that mention a wave are history and were
  left as they are.

## Verification

All run on Linux in a cloud checkout of `78ab9b9`, not on the owner's machine.

- `uv run ruff check src tests scripts`: passed (component).
- `uv run mypy --platform win32 src tests scripts/export-contracts.py`: no issues in 359 files
  (component). Without `--platform win32`, Linux reports 41 errors, all from Windows-only APIs.
- `uv run python scripts/export-contracts.py --check`: schemas are fresh (component).
- Motion tests (`tests/providers`, `tests/embodiment`, `tests/decision`, the move-intent,
  move-target, companion-call and companion-presentation tests, and voice parity): 310 passed /
  10 skipped (component; the skips are opt-in hardware and model tests).
- Full suite: 1130 passed / 33 skipped / 4 xfailed / 8 failed. All 8 failures are Linux-only:
  Windows paths such as `C:\project` are not absolute on Linux, and the Codex adapter looks for
  `python.exe`. None involves motion.

Not run: the C# client tests, the desktop shell build, the Unity PlayMode tests, the Windows
player build, and any live check with E4B.

## Limits and next

- **Rebuild the avatar on the owner's machine:** quit SORA, then run
  `.\scripts\build-embodiment.ps1`. This runs the PlayMode tests and builds the player. Until
  then the installed avatar still carries the old waving state, although Core no longer sends
  it.
- Then check V1 step 5 live: "wave to me" should give a reply without a motion, and "walk over
  here" should walk her to the pointer.

HOW_TO_USE.md: updated in the code change (Last updated 2026-10-12 09:40); no further change.
