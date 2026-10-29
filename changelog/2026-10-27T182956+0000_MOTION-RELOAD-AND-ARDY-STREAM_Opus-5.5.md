# Reload motion model: Core runs ARDY live and her player plays its stream

Model name: **Opus 5.5**. Checkpoint **2026-10-27 18:29:56 +00:00**. Status: **implemented**.
Her player was not tested against a live model end to end (see Limits).

Follows [MOTION-MODEL-SETTINGS-AND-WINDOW](2026-10-27T021500+0000_MOTION-MODEL-SETTINGS-AND-WINDOW_Opus-5.5.md),
whose "Not connected yet" this replaces. The owner asked for the same Reload button the brain
has: stop the old motion process, start the new one, and pass her last 2 to 3 seconds of
motion to the new model so it carries on from what she was doing.

## Changes

**Core**
- `src/sora/embodiment/motion_service.py` (new): `MotionSupervisor`. A reload:
  1. stops the current model;
  2. tells her player to keep her own poses and record;
  3. starts motion-lab's `ardy-runtime/service.py` (fp16/fp32, the chosen number of diffusion steps);
  4. asks the player for its recording once the model is ready (it starts standing if none comes
     within 3 s);
  5. relays the model's 0.4 s chunks;
  6. switches her over after the first chunk.

  A model that fails to load leaves her on the algorithmic system, with the reason shown. Custom
  versions are refused ("only ARDY").
- `src/sora/contracts/motion_stream.py` (new): the messages, relayed as `embodiment.motion` on the
  embodiment WebSocket beside `embodiment.voice`. They are now public contracts
  (`motion-stream-core-message`, `motion-stream-player-message`), with the schemas exported.
- `src/sora/api/motion_routes.py`: `GET /api/v1/motion/status`, `POST /api/v1/motion/reload`.
  `server.py` relays the motion messages, and `__main__.py` starts the saved engine at boot.
- `runtime/app_settings.py`: the `motion.*` settings now apply with Reload motion model (a new
  `motion_reload` tier) rather than a restart.

**Her player (Unity)**
- `Network/SoraCoreClient.cs`: motion DTOs with validation (unit quaternions, 22 joints, at
  most 64 frames). A malformed message is dropped and the connection carries on.
- `Avatar/AvatarMotionStream.cs` (new):
  - plays chunks on a clock 0.5 s behind what has arrived, slowing or speeding it by up to 5%
    to hold that buffer;
  - blends between engines over 0.3 s, and goes back to her own poses if chunks stop for 2 s;
  - takes the model's smoothed heading off her hips, so SORA still owns her facing and position;
  - keeps the last 3 s of her realised pose at 20 fps for the seed.
- `Avatar/AvatarPhysicsBody.cs`: while a model moves her and she stands, its pose becomes the
  motor targets in place of SORA's animation and the stand-in gait. Her hips height follows the
  model's, and a running model's flight phase doesn't count as a fall. Physics, falls and being
  held are unchanged. It also records her realised pose (her facing on screen taken off).
- `Network/SoraEmbodimentBehaviour.cs` and `SoraBootstrap.cs`: motion messages are queued to
  the main thread, and the seed is sent on request. Every 0.4 s, or as soon as what she is doing
  changes, the player sends a signal:
  - an intent from what she is doing: idle, walk, run, sit, lean, climb or fall;
  - a velocity: SORA's speed along the model's own facing, zero when she isn't travelling.

  Emotion isn't sent yet (`-`).

**Panels**
- Motion window: a **Reload motion model** button in its banner, and a status banner that polls
  while a model starts (starting, handing over, running, failed). The wording now says changes
  apply on reload. `shared/api.js`: `motionStatus`, `reloadMotion`.
- Settings: the tier label for `motion_reload`.

## Verification

| Kind | What ran | Result |
| --- | --- | --- |
| Suite | `scripts/verify.ps1` | Passed: ruff, strict mypy on 368 files, the schema check, pytest 1161 passed / 26 skipped / 4 xfailed, compileall, 148 panel tests |
| Component | `dotnet test clients/csharp_tests` | 422 passed |
| Build | `dotnet build clients/desktop_shell` | 0 warnings, 0 errors |
| Component, fake service | `tests/embodiment/test_motion_service.py` | 7 tests, included in the pytest count |
| Native, Unity PlayMode, made-up chunks | `build-embodiment.ps1 -TestOnly` (no player build) | 92 passed, 2 failed. One P19 test was mine and expected the wrong thing: it ran past the 2 s stale limit. That is fixed. The other was the P18 head-drop test: 1.36 against a limit of 1.2, while `verify.ps1` was running at the same time |
| Native, re-run on its own | P18 + P19, filtered | 15 / 15 passed, the head-drop test included |
| Live model, no player | Core's `MotionSupervisor` with the real ARDY service (fp16, 4 steps, DirectML), driven by `.local/motion-stream-qa-2026-10-27/live_supervisor.py` | See below |

The P19 tests (on her real physics body, with fixture chunks) check that:
- the model's pose raises her arm above her head without a fall;
- she goes back to her own idle pose when the chunks stop;
- her recording is 60 frames at standing hips height, facing +Z;
- the clock buffers, blends, waits at a late chunk, and lets a newer plan replace what it overlaps.

The live run with the real ARDY service:
- it loaded in **25.9 s**;
- Core asked for the seed, took a 60-frame standing seed and switched to `ardy`;
- 40 chunks arrived, a median 0.406 s apart (worst 0.437 s);
- asked to walk at 1.2 m/s, it walked at **1.17 m/s** over 11.6 s;
- switching back to algorithmic stopped the process, with exit code 0.

Evidence is in `.local/motion-stream-qa-2026-10-27/`.

## Limits and next
- **Not run end to end:** her built player with Core and ARDY together, on screen. The owner's
  player wasn't rebuilt (it may be running). The next build of her player will contain this.
  The first live look should check three things: that the walk looks right at SORA's speeds,
  that the heading removal holds her straight, and that the hand-over from her own poses is
  smooth.
- **Load time is about 26 s, not the 2 to 3 s planned.** Most of it is Python, torch and the
  DirectML session starting up. The recording is always on, so the seed is still her last 3 s
  before ARDY is ready.
- The P18 head-drop test missed its limit once under load and then passed on its own. Watch for
  it under load.
- Not sent yet: emotion and intensity. Not checked yet: gaze, reach and voice gestures while the
  model owns her. They reach the physics body through SORA's animation, which the model's pose
  replaces, so they may be lost until they are layered on top.
- Custom trained versions can't drive her yet.

HOW_TO_USE.md: updated (Motion: Reload motion model, the load time, what ARDY is told).
