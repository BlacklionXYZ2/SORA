# "Wave" removed: it only walked her on the spot, so walking is the walk

Model name: **Opus 5.5**. Checkpoint **2026-10-12 19:55:00 +01:00**, Europe/London. Status:
**implemented and verified**. The owner committed the edits in `78ab9b9` ("updates", 09:03), and
they were checked again after pulling the W5 web panels (`992747a`).

The owner: "Yes, change wave to walk." This followed my question whether to stop offering the
"wave" pose, which only walked her on the spot (see the
[09:00 entry](2026-10-12T090000+0100_WAVE-IS-A-WALK-DOCS_Opus-5.5.md)). There is now no wave
anywhere; asking her to walk uses the real walk, which moves her. This keeps V1 step 5 honest.

## Changes

**Core (the brain's vocabulary):**
- **`contracts/motion.py`:**
  - `MotionKeyword` and `MOTION_STATES` no longer have `wave`;
  - the motion prompt says she has no wave or other gesture, and its example "Wave to me" now
    chooses none.
- **`contracts/companion_call.py`:**
  - `PoseName` is sit, lean, climb or stand;
  - the call prompt says there is no wave, and its arrival example is "go over to Spotify and
    lean".
- **`contracts/embodiment.py`:** `EmbodimentPresentationState.WAVING` removed.
- **Runtime:**
  - `move_intent.py` no longer has a wave arrival pose;
  - `read_turn.py` (her abilities) and `service.py` (the Core action note) no longer list wave;
  - `local_player.py` no longer accepts the `waving` state.
- **`decision/families.py`:** the motion family Laya reads is now "walking, running, sitting".
- **Public schemas re-exported:** `companion-call`, `motion-choice`, `embodiment-command` and
  `embodiment-state`.

**Avatar player and the old app:**
- The Unity `waving` profile was removed (`PresentationProfileRegistry.cs`), and so was its
  entry in `SoraCoreClient.cs`'s accepted states.
- The frozen full app (`FullAppForm.cs`) lost its Wave preview button.

**Tests:**
- Every Python, C# and Unity test that used wave as an example pose now uses sit or climb.
- New checks that `{"motion":"wave"}` and `{"op":"pose","name":"wave"}` are rejected.
- `owner_move`: waving words no longer choose an arrival pose.

**Decision-layer seed labels:** "Say hi with a wave" (train) and "Give me a wave" (eval) now need
no tool families. Messages that also ask her to move keep `motion`.

**Docs:**
- [HOW_TO_USE.md](../HOW_TO_USE.md): she has no wave; ask her to walk.
- [V1.md](../V1.md) step 5's note.
- `docs/runbooks/SORA_MOTION_KEYWORDS.md` (keyword list and table) and
  `docs/runbooks/SORA_LOCAL_TRYOUT.md` (preview buttons).
- The launcher comment in `scripts/start-full-sora.ps1`.

Dated records that mention the old keyword are left as written: the implementation plan's
progress notes, V1's status rows and older plans.

## Verification

- **Unity, native:**
  - PlayMode: 63 passed / 0 failed (`Sora.Embodiment.PlayModeTests`, batch mode, Unity
    6000.6.0f1);
  - the Windows player was rebuilt in place ("Build Finished, Result: Success";
    `Sora.Embodiment.dll` written at 08:55);
  - the logs are in the session's scratch folder, so the repository's earlier Unity evidence
    logs were left as they were.
- **After the pull (`992747a`):**
  - `.\scripts\verify.ps1` exited 0: ruff, `mypy --strict` (361 files), the schema check,
    `pytest` (1145 passed / 26 skipped / 4 xfailed), compileall and the panel tests;
  - `dotnet test clients/csharp_tests`: 420 passed;
  - `desktop_shell` and `desktop_app` build.
- **Not run:**
  - a live chat check that "wave to me" now gets no motion and a polite "I can't wave";
  - the opt-in real-model motion test, whose probes were updated: "Wave to me with your avatar"
    now expects none.

## Limits and next

The owner's running copy needs nothing extra: the player at `clients/unity/Builds/Windows` is
already rebuilt, and Core picks up the change the next time SORA starts.

HOW_TO_USE.md: updated.
