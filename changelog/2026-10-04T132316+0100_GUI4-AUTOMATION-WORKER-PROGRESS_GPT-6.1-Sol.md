# GUI-4 Automation worker progress

Model name: **GPT-6.1 Sol**. Source/component checkpoint **2026-10-04 13:23:16 +01:00**, Europe/London. Status: **implemented source slice; GUI-4a/c in progress**, not stage completion.

## Changes implemented

- Added one Core-owned bounded periodic scheduler with ordinal continuation, injected clock support, due/missed/overlap reservations, startup and shutdown lifecycle, synchronous managed-shutdown admission fence and safe repeated/cancelled cleanup.
- Added transactional admission guards and original task/run/submission linkage inside existing task admission. Rechecks definition/version/state/behavior, overlap, current static policy/provider and delegation epoch; no new agent executor or direct file-writing capability.
- Added exact-key recovery, stale reservation retirement, bounded recovered/live missed-run handling, future reservation waiting after clock rollback, original-run evidence validation and canonical outcome reconciliation. Unknown effects remain Unknown, including failed-status runs whose outcome is Unknown; no automatic retry/replay. Completion requires stored matching task/run/result evidence.
- Hardened cancelled admission and commit-to-queue handoff so committed work is settled/queued exactly once before optional trace recording. Event failure rolls back task/run/submission/linkage together.
- Extended current/historical API scheduler-state enums truthfully; list/detail reflect actual loop, durable save receipts remain historical. Re-exported three affected API schemas without adding a migration or changing settings/default client.
- Added 28 worker/integration/recovery/lifecycle cases; retained storage tests by explicitly stopping their timing loop when using historical injected clocks. Wrote worker contract/report and reconciled roadmap/runbook current state while preserving prior checkpoints and completed dates.

## Verification and next scope

[Verification report](../docs/verification/GUI4_AUTOMATION_WORKER_GPT-6.1-Sol_2026-10-04.md): 67 final focused Python passes; 369 C# regression passes, three zero-warning/error Windows builds and effect-free forwarding. Final full isolated process85599 result is appended after observed terminal completion, not inferred from collected tests.

Actual temporary Core reopen and deterministic owned scheduler loop are verified, not owner restart/live-provider/native acceptance. Owner runtime/environment/data/settings and reference originals preserved. GUI-4a/c and the full GUI goal stay active; next durable manual Run now, shared Automations UI and connected scheduled-run/native acceptance. Earlier GUI gates, real graph/design and ordinary-release work remain required. No completion checkbox/time added.

Final full isolated regression observed **2026-10-04 13:27:37 +01:00**, same process85599 terminal exit0: **890 Python passed /25 opt-in skipped in105.52 seconds; 8 PWA; mypy286/lint/exported-schema/compilation passed**. Only documentation changed afterward. Earlier888/889 totals were superseded after final cleanup/clock-rollback coverage. No whole-stage completion time added; roadmap nowv1.31.

## Documentation and preservation checks

**2026-10-04 13:30:45 +01:00:** 189 local links checked across seven current roadmap/contract/report/runbook/changelog files; zero broken targets. All five reference originals retain manifest byte counts/SHA256 hashes. Exactly three stage boxes remain checked, each retaining **2026-10-03 19:24:55 +01:00**. Tracked `git diff --check` passed. Owner Core PID52000/start **2026-09-29 21:49:32**, `.venv/Scripts/sora.exe`, rechecked unchanged.

Immediate pre-worker 1,064-file SHA256 fingerprint (includes `uv.lock`, excludes `SORA.zip`): 1,051 original files unchanged, 13 declared existing files changed, six additions, no missing originals. Changes are task service/repository, routes, Automation API/store, three affected exported API schemas, the storage test timing fixture and four current roadmap/runbook/contract documents. Additions are worker/admission source, worker tests and the three new documents. Earlier verification/contributor logs, reference originals, clock/spec source, migrations, settings/default-client source, `pyproject.toml` and `uv.lock` unchanged. This is a preservation check, not a backup or commit.
