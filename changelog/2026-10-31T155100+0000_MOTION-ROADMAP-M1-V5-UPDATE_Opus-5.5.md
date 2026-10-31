# Motion-core roadmap: M1 status brought up to date (v5 through the foot-lock runs)

Model name: **Opus 5.5**. Checkpoint **2026-10-31 15:51 UTC**. Status: **documented**.

The owner (2026-10-31) asked for the documentation of the new training runs. The previous
roadmap status (2026-10-30 15:35) stopped at `latent-vel-free5`.

## Changes in SORA

- `docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`, M1's v5 status, updated in place:
  - **steering and facing:** free7, free8;
  - **the foot lock**, with the ground lock, the flight limit and the cap;
  - **where it stands after 25 runs:**
    - `latent-vel-lock-sup` is alive and on planted feet, but doesn't follow commands;
    - the foot-locked free-run fine-tunes collapsed;
    - two runs are training;
  - **two findings:** the memory drift, and that validation doesn't predict long runs.

Details are in motion-lab's `versions/v5/README.md` and its changelog. No SORA code changed, and
no gate is ticked. Nothing committed.
