# Motion-core roadmap: M1 status for v5

Model name: **Opus 5.5**. Checkpoint **2026-10-30 15:35 UTC**. Status: **documented**.

The owner (2026-10-30) asked for the motion core to be improved iteratively by research, training
and testing aimed at unusual behaviour. The work is in motion-lab and logged in its changelog
(2026-10-30 entries: `MOTION-V5-STRESS-BATTERY-AND-LATENT`, `MOTION-V5-FIRST-RESULTS-AND-FREE-RUNS`,
`MOTION-V5-FREE-RUNS-SAMPLING-AND-MEMORY` and `MOTION-V5-FREE4-FREE5-RESULTS`; and for ARDY,
`ARDY-STRESS-IDLE-ANCHOR-AND-GET-UP` and `ARDY-ANCHOR-HEIGHT-AND-GESTURES`).

## Changes in SORA

- `docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`, M1 status, updated in place:
  - what the v5 stress battery found in v4;
  - the four steps that ended the freezing;
  - the best model so far (`latent-vel-free5`), with what is sound and what is open;
  - the memory-drift finding.

No SORA code changed. No gate is ticked: M1's gate also needs the owner's judgement of idle
motion, and nothing has been viewed on Alice.

Nothing committed.
