# Motion core M0 (foundations and specs): evidence

Observed by **Opus 5.5**, 2026-10-11, on the owner's PC. Code in `~/Desktop/motion-lab`
(uncommitted); spec `motion-lab/docs/M0.md`; plan
[MOTION-CORE-ROADMAP_2026-10-11](../plans/MOTION-CORE-ROADMAP_2026-10-11.md), stage M0.

**Evidence kind:** component tests and measurements in Python (PyTorch 2.12.0 with ROCm 7.14, run
on the CPU), plus an ONNX export checked against onnxruntime. Not run: Unity (the runtime spike).

## What was built

- **`rotation.py`:**
  - 6D↔R; SO(3) Exp and Log, with a symmetric-part branch beyond π/2;
  - body-frame integration that re-projects onto SO(3), and finite-difference ω;
  - geodesic distance and mirroring;
  - angles from `atan2` with clamped square roots, for finite gradients.
- **`vrm.py` and `scripts/build_skeleton.py`:** read her VRM 1.0 (Seed-san, SHA-256
  `624d0d55…`) and write the canonical skeleton asset, after checking:
  - hierarchy, facing (+Z) and handedness (her left = +X);
  - symmetry and ground contact.
- **`skeleton.py`:** 21 joints (her humanoid body: no fingers, no eyes, no upperChest), parents,
  mirror pairs, world-aligned rest frames, and placeholder limits.
- **`fk.py`:** forward kinematics.
- **`formats.py`:**
  - 60 Hz clips with validation, and 2 s windows;
  - the 192-number motion state (6D, ω from the realised pose, root velocity in her heading
    frame);
  - mirror augmentation.
- **`motion_signal.py`:** the frozen v1 schema (audio `rms`, `voiced`, `pitch`, `onset`;
  valence and arousal), and a 26-number feature vector.
- **`export.py`:** a per-tick `StepModel` stand-in (527k parameters) exported as one ONNX file,
  plus a parity check.
- **`scripts/setup-env.ps1`:** a `.venv` that reuses the owner's ROCm PyTorch; adds onnx,
  onnxscript and ruff.

## Gate measurements (`scripts/m0_gate.py`, 2026-10-11 20:36 UTC)

| Gate (roadmap, proposed thresholds) | Limit | Measured | Result |
|---|---|---|---|
| 6D → R → 6D round trip (100,000 random rotations, float32) | < 1e-5 | 2.4e-7 | Passed |
| Orthonormality after 100,000 integration steps (256 chains, float32) | < 1e-4 | 7.2e-7 | Passed |
| FK of the rest pose reproduces the rest positions | < 1e-6 | 0.0 | Passed |
| ONNX vs PyTorch, 600 ticks with hidden-state feedback | < 1e-5 | 1.7e-6 | Passed |
| Exp/Log inverse, float32, angles to π − 0.01 (recorded) | n/a | 5.7e-7 | n/a |
| Skeleton left/right symmetry from the VRM (recorded) | 5 mm | 0.0 mm | n/a |

**Tests:**
- 29 passed (`.venv\Scripts\python -m pytest`), covering all of the above;
- Log at angles of 0, 1e-7, π − 1e-6 and π;
- finite gradients for the geodesic loss at identity and near π;
- ω recovered from a spinning joint;
- heading-frame root velocity unaffected by facing;
- mirror round trips;
- schema and Python agreement;
- a hand-computed FK chain.

ruff is clean.

**Found and fixed while testing:**
- the geodesic loss's gradient was NaN at the identity, the most common case in training, from
  √0 in both the angle and Exp;
- float32 Log lost accuracy near π;
- the dynamo exporter wrote its weights to a separate file, so it now writes one self-contained
  file for Unity.

## Not done (M0 stays open)

- **The skeleton table reviewed line by line by a second agent** (the roadmap's gate). Automated
  checks passed (hierarchy, facing, handedness, symmetry, ground), but the independent review
  hasn't happened.
- **The Unity runtime spike** (doesn't gate M0): first check whether Sentis supports the ONNX
  `GRU` operator in the exported graph, then measure per-tick cost at 60 Hz.

## Addendum, same evening: 22-joint canonical skeleton and the avatar adapter

The owner asked to train on the correct joints and deal with an avatar's missing ones separately,
rather than merging joints in the training data. So:

- **The canonical skeleton is now the full VRM humanoid body, 22 joints** (`upperChest` added).
  AMASS and LAFAN1 both have a three-joint spine, so they map one to one.
- **Seed-san has no `upperChest`,** so the canonical rest pose places one 0.436 of the way from
  chest to neck. That figure was measured on `sister1.0.vrm` (N.E.K.O's VRM 1.0 avatar, which
  has one; 7 mm off the line) and is recorded in the asset.
- **New `adapter.py`:** maps the 22 joints onto any avatar's joints by composing rotations:
  - a missing leaf is dropped;
  - a missing only child folds into its parent;
  - a missing joint with siblings folds into its child.
- **Measured on Seed-san:**
  - every joint she has takes the exact orientation of the last canonical joint folded into it
    (max difference < 1e-5);
  - positions above the fold shift by up to 1.8, 3.5 and 5.2 cm with the upper chest bent 10°,
    20° and 30°, and by 0 when it's straight.
- **After the change:**
  - 32 tests passed; ruff clean;
  - `m0_gate.py` re-run: all four gates pass (ONNX parity 1.5e-6; `StepModel` 531k parameters;
    motion state 201 numbers).
- **Lynae (Sketchfab, suggested by the owner) was not used.** The canonical body's joints come
  from the VRM standard and the datasets, so no other character model is needed.

## Addendum, 2026-10-12: Alice's proportions

The owner made **Alice** SORA's default avatar (2026-10-11), so the canonical skeleton is now
built from her VRM instead of Seed-san's.

- **Alice.vrm** is VRM 0.x (SHA-256 `985df203…`), from VRoid Hub, with credit: original model by
  miHoYo, VRM by Niko. Her licence forbids modification and redistribution, so the file stays in
  SORA's `.local/avatars/` (outside git) and is only read.
- **`vrm.py` now reads VRM 0.x as well as 1.0.** VRM 0.x models face −Z, so positions are turned
  180° about the vertical to face +Z (detected from the toes, which must be in front of the
  feet). The asset records `vrm_version: "0.x"` and `turned_to_face_plus_z: true`.
- **Her skeleton** (`build_skeleton.py`, 2026-10-12 06:45 UTC):
  - 21 of the 22 joints: no `upperChest`, which is placed by the same measured 0.436 rule;
  - hips 0.8946 m and head 1.3335 m above the ground;
  - left/right asymmetry 0.03 mm.
- **Adapter fold on Alice:** with the upper chest bent 10°, 20° or 30°, positions above it shift
  by at most 1.5, 3.0 or 4.4 cm, and by 0 when it's straight. The same script reproduces
  Seed-san's 1.8, 3.5 and 5.2 cm.
- **`m0_gate.py` re-run on Alice's skeleton (2026-10-12 06:46 UTC):** all four gates pass:
  - 6D round trip 2.4e-7;
  - orthonormality 7.2e-7;
  - FK of the rest pose 0.0;
  - ONNX parity 1.5e-6.
- **Tests:** 33 passed; ruff clean. The adapter test runs on both Alice and Seed-san, each
  against the canonical skeleton at that avatar's own proportions.
- **Fixed on the way:**
  - the documented `python scripts\build_skeleton.py` couldn't import `motionlab`;
    `setup-env.ps1` now puts `src` on the `.venv`'s path;
  - `turned_to_face_plus_z` was written as the string `"True"`; it is now a boolean.

**Evidence kind:** component (Python, CPU). Alice's avatar in SORA's Unity player is separate
evidence, in the changelog `2026-10-12T080000+0100_AVATAR-ALICE-DEFAULT_Opus-5.5.md`.
