# Alice is SORA's default avatar; permission traces no longer flood the database

Model name: **Opus 5.5**. Checkpoint **2026-10-12 08:00:00 +01:00**, Europe/London. Status:
**implemented and live-checked in an isolated profile**; the owner's own SORA has not been
restarted or touched.

The owner uploaded `Alice.vrm` and said: "Alice will be the new default model." This moves V1
step 1 (she appears on the desktop), step 5 (wave, sit, walk) and step 8 (Settings) forward.

## Changes

**Alice as the default avatar (SORA):**

- **New `src/sora/embodiment/avatar_settings.py`:**
  - `AvatarSettings.vrm_path`, default `.local/avatars/Alice.vrm`;
  - `resolve_avatar()`, which falls back to the built-in Seed-san for a blank path, a missing
    file or a file that isn't `.vrm`;
  - the credit line.
- **`app_settings.py`:** a new `avatar` section.
  - The field is **Avatar model (VRM)**, under Appearance → Avatar; it is a file path that
    applies at the next start.
  - Settings saved before 2026-10-11 load with the default.
- **`__main__.py`:**
  - an explicit `--avatar-path` still wins; otherwise the setting decides;
  - a missing file prints a message and uses Seed-san.
- **The file** is at `.local/avatars/Alice.vrm` (SHA-256 `985df203…`). It is gitignored and
  never edited: her VRoid Hub licence requires credit and forbids modification, redistribution
  and commercial use. Unity loads the VRM 0.x file with the existing `canLoadVrm0X: true`, so no
  rebuild is needed.

**Settings window (web panel):**

- **An Appearance category** (after General) shows the avatar field. Core already sent the
  field, but the panel's category list had no Appearance, so the field was unreachable.
- **The older Appearance window** (window style, Chat shortcut, placement) is now opened by a
  button in that pane. The rail's separate Appearance button is hidden while the category is
  listed.
- **`clients/panels/tests/fixtures/settings-projection.json`** was regenerated from Core: it
  held 140 of the 145 fields, which is how the gap got past the panel tests. The test now checks
  the Appearance category and the avatar field.

**Permission traces (a bug found while checking Alice):**

- **The bug:** `SoraRuntime.authorize_operation` wrote an `operation.owner_policy` trace for
  every owner-local check. The avatar's embodiment calls are checked about 37 times a second, so
  the owner's `.local\manual-test\data\sora.db` had grown to 934 MB, with 2,154,370 such rows
  from 2026-10-04 to 2026-10-09.
- **The fix:** identical checks (same operation, effects and settings revision) are traced at
  most once a minute. Each trace carries `identical_since_last`, the number of checks it stands
  for. A settings change or a different kind of check is traced at once.
  `OWNER_POLICY_TRACE_INTERVAL` is in `service.py`.
- **New test:** `tests/runtime/test_owner_policy_traces.py`.

**motion-lab** (`~/Desktop/motion-lab`, uncommitted):

- **`vrm.py`** reads VRM 0.x as well as 1.0, turning 0.x models (which face −Z) to face +Z.
- **The canonical skeleton** is rebuilt from Alice's proportions: hips 0.89 m, head 1.33 m.
- **`build_skeleton.py`:**
  - Alice is the default VRM, and Seed-san is `SEED_SAN`;
  - `turned_to_face_plus_z` is now a boolean (it was written as the string `"True"`).
- **`setup-env.ps1`** puts `src` on the `.venv`'s path. Before this, the documented
  `python scripts\build_skeleton.py` failed with "No module named 'motionlab'".
- **Docs:** `docs/M0.md` updated for Alice; the adapter test runs on both avatars.

**Docs:**

- [HOW_TO_USE.md](../HOW_TO_USE.md) covers her look: the credit, where the file lives, how to
  change it or go back to Seed-san, and Settings → Appearance.
- The motion roadmap's rule 4 and M0 status.
- An addendum to [the M0 evidence](../docs/verification/MOTION_M0_Opus-5.5_2026-10-11.md).

## Verification

- **Component (Python):**
  - `.\scripts\verify.ps1` at 08:05 exited 0: ruff, `mypy --strict` (361 files), the schema
    freshness check, `pytest` (1142 passed / 26 skipped / 4 xfailed), compileall and the panel
    tests.
- **The trace test fails without the throttle.** With the interval set below zero, the
  50-identical-checks assertion fails.
- **Component (panels):** `node --test`: 33 passed. Before the category was added, the
  regenerated fixture made the test fail with 144 of 145 fields reachable.
- **Component (motion-lab):**
  - 33 tests passed; ruff clean;
  - `m0_gate.py` on Alice's skeleton: all four gates pass (ONNX parity 1.5e-6);
  - the adapter's shift above her folded `upperChest` is 1.5, 3.0 and 4.4 cm at 10°, 20° and
    30°.
- **Native and live, isolated profile.** Core ran with the real Unity player on this PC, in
  `.local\alice-avatar-qa-2026-10-12` (the settings were copied, and the deterministic dialogue
  backend was used):
  - **Alice loaded:** 310 spring joints, connected, with the topology reported (two monitors).
  - **Wave, sit and walk:** sent through `POST /api/v1/embodiment/command`.
    - Wave and sit reached the states `waving` and `sitting`.
    - The walk moved her 500 px left and back (3071 → 2571 → 3071).
    - Screenshots of her surroundings only are in `shots\`. They show her standing, sitting,
      and walking in profile.
  - **The trace throttle in the same run:** 2 `operation.owner_policy` traces in one minute.
    The second recorded `identical_since_last: 2194`, so it replaced about 2,196 rows.
- **The wave is weak, and not because of Alice.** In a frame-by-frame burst, her right hand
  comes forward only to waist height. Seed-san, in `.local\seed-san-wave-qa-2026-10-12`, does
  exactly the same. The waving profile pitches the upper arm 55° forward with a 24° pulse
  (`PresentationProfileRegistry.cs`, `AvatarIdlePose.cs`), so the hand never rises above the
  shoulder.

## Limits and next

- **Not run:**
  - the owner's own SORA. It picks up Alice the next time it starts, because the owner's
    settings have no `avatar` section, so the default applies;
  - a spoken or model-chosen wave;
  - C# tests, since no C# changed;
  - a visual check of the Settings panel's new Appearance pane.
- **During Alice's walk her ponytail streams straight out behind her.** Her spring settings may
  need tuning.
- **The wave:** offered to the owner as a small Unity fix (raise the arm to the side, above the
  shoulder). It needs a player rebuild.
- **The owner's 934 MB database is unchanged.** Pruning old `operation.owner_policy` rows is
  offered; it has not been done.
- **Nothing is committed in either repository.**

HOW_TO_USE.md: updated.
