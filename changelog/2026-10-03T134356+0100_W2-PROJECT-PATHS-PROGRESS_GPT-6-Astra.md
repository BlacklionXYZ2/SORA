# W2 selected projects and writer evidence — GPT-6 Astra

Delivery checkpoint: **2026-10-03 13:43:56 +01:00** (Europe/London).
Stage status: **progress**. Implemented/tested slice, not complete W2 or frontend goal.

## Changes implemented

- Canonical settings v8: per-agent actual project directory, direct/isolated/read-only mode, base ref,
  legacy backups and GUI-editable new-run specialist deadline (300 seconds default, 5–3600 range).
- Persistent per-task project/mode/model selection through API, shared delegate/board controls and
  provider requests. Missing write destination asks Which project; no implicit SORA folder/fallback.
- Codex selected-project direct editing, explicit isolated worktrees and read-only mode; fresh native
  thread/focused context and native sandbox policy. Unsupported Hermes/Antigravity boundaries are
  typed and visible, not silently replaced. Owner native-agent configuration remains untouched.
- Database migration 10 for atomic overlapping writer reservations and source-labelled path evidence.
  Conservative reconciliation/uncertainty; no time-based unlock. Bounded metadata diffs exclude
  Git/reparse traversal and disclose partial coverage without copying file bodies.
- Waiting-bootstrap Windows job attachment before writer launch, owned-tree termination and retained
  stop proof before normal root release. Bound adapter cancel/steer routing and stubborn-turn cancel.
- Shared Paths GUI, Activity project/mode plus explicit result button, readable results/errors/
  reported changelog and coverage. Repaired overflow, Browse clipping, DPI initialization and
  submission-time Browse disabling. Remote task/replay snapshots omit new private root fields.
- Added deterministic project/dirty-file/overlap/migration/reconciliation/cancellation/privacy tests
  and no-inference native sandbox/junction/read-only verification script.
- Updated agent runbook and additive plan/tracker notes without closing or narrowing other scope.

Primary implementation areas: `contracts/models.py`, `persistence/migrations.py`, runtime settings/
repository/service/catalogue/project_paths, `providers/codex.py`, new `providers/windows_job.py` and
`writer_bootstrap.py`, API routes/events, shared Windows catalogue/Paths/result forms and sync/models,
full-app Activity/board, settings example/generated schemas and relevant tests.

## Verification

- Final standard gate: **608 Python passed / 24 opt-in skipped**, 119.42 seconds; Ruff, mypy (248
  files), generated-contract check, compileall and **8 PWA checks** passed.
- **41 C# tests** passed; both Windows clients build with zero warnings/errors.
- Native no-inference Codex command probe: inside write succeeds; outside and junction-target writes
  denied; outside read succeeds; read-only write denied. Private proof retained in `.local/...-r8`.
- Real low-cost Luna/low attempt changed the QA marker and authored a readable file, but **failed**
  the prior 30-second Core deadline before final JSON. The new deadline and attribution instruction
  address observed defects; successful post-fix live completion remains unverified. A second launch
  was policy-blocked and not retried via another channel. No higher-cost specialist was used.
- Actual Computer Use reviewed/repaired Paths source columns/coverage, Activity, explicit readable
  failed result, Settings fields, project selector/Browse and cancel-preserved draft. Final selector
  was cancelled, not submitted. No full successful GUI write is claimed.
- Earlier kernel test attempts failed on conservative PID reopening during termination. Final tests
  retain the original process handle and assert signalled exit plus zero active named-job members.
  Controlled child stdio was isolated to repair its delayed startup; stop assertions were preserved.
- QA GUI closed; exact owned QA Core chain force-stopped and port released. Owner Core **52000**
  remains alive/unchanged. QA artifacts retained; no material files removed, no commit created.

Detailed evidence and remaining gates:
[W2 project paths](../docs/verification/W2_PROJECT_PATHS_GPT-6-Astra_2026-10-03.md).
Successful post-fix real-model/GUI changelog, full crash/alias matrix, amendments/renewals, every
adapter boundary, compact/PWA UX, multi-model shortlist/CompanionCall and all other alignment
requirements remain active. Existing owner Core needs a normal restart to load the new backend.
