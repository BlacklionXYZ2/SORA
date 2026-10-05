# GUI-4 Automation worker verification

Model name: **GPT-6.1 Sol**. Final source/component checkpoint **2026-10-04 13:23:16 +01:00**, Europe/London. Status: **source slice verified; GUI-4a/c in progress**. [Contract](../gui/GUI4_AUTOMATION_WORKER_CONTRACT_GPT-6.1-Sol_2026-10-04.md).

## Fresh evidence

- **67 focused Python passed in 13.11 seconds**: 28 new worker cases, 22 storage/API cases and 17 existing lifecycle cases. Last focused process12596 returned terminal exit0 at13:23:16. Storage-only tests explicitly stop the new real timing loop before using historical injected clocks; this preserves their storage assertions instead of allowing timer interference.
- **369 C# component tests passed**, no failures/skips, three Windows builds with zero warnings/errors and effect-free launcher forwarding at **13:18:48 +01:00**. No C# source/test changed; these are regression, not Automations UI acceptance.
- Final isolated `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` is process85599. Lint and mypy286 passed; 915 tests collected. Its final result is appended only after that same process is observed terminal. Earlier passes888/889 excluded subsequently added cleanup/clock-rollback coverage and are not the final-source result.

Focused coverage includes actual task/original-run/submission linkage and validated-result completion; future/no admission and concurrent-tick dedup; pause/edit/delete before admission; atomic event failure rolling back task/run/submission; commit-before-trace-failure queue handoff; cancellation in the SQLite admission thread after the guard, with one legitimate committed/queued task; pause/stop/static-policy changes during awaited provider metadata; existing exact submission reconciliation without resubmission; default skipped and bounded run-once reservations after an actual temporary Core reopen; long-delayed live reservations and wall-clock rollback; Unknown normalized outcome under failed run status, missing completed-result evidence, interrupted/replaced original run, definite provider failure, overlap skip and no automatic retry; corrupt-record/batch continuation; one actual owned loop completing a deterministic-provider task; single worker/repeated cancelled cleanup; authenticated HTTP current availability versus historical receipt.

No sleep-only success assertion substitutes for task evidence. Injected clock/event/thread barriers make the boundary deterministic. The actual owned-loop test uses a 50ms loop interval and injected time; this proves scheduler-to-canonical-task integration, not real wall-time reliability or a live provider. Actual reopen uses only the fixture's temporary profile/database, not the owner's Core.

Initial draft failures were corrected and rerun: SQL event lookup used a nonexistent column then an empty filter, so it now checks the real JSON `event_type` and requires nonempty events; Unknown outcome classification was strengthened; postcommit trace injection was narrowed to the admission trace so it does not deliberately sabotage the task worker too; full mypy required typed test action/dict/nullable narrowing. No failing result is described as passing.

## Final full regression

**2026-10-04 13:27:37 +01:00:** Same isolated process85599 returned terminal exit0. Final-source `./scripts/verify.ps1`: **890 Python passed /25 opt-in skipped in105.52 seconds; 8 PWA checks; mypy286/lint/exported-schema checks/compilation passed**. Source/tests/schemas unchanged after the final run began; only documentation changed afterward. Earlier888/889 runs are not substituted for this final result.

## Preservation and acceptance boundary

**13:30:45 +01:00:** 189 local links across seven current documents resolve, five reference originals match manifest bytes/SHA256, and the three checked stages retain their original completion timestamps. Immediate pre-worker 1,064-file fingerprint: 1,051 unchanged originals, 13 declared changed originals, six additions, no missing files. Tracked diff whitespace check passed; owner Core process/start/path rechecked unchanged. Detailed paths/scope are in the [progress changelog](../../changelog/2026-10-04T132316+0100_GUI4-AUTOMATION-WORKER-PROGRESS_GPT-6.1-Sol.md).

Owner Core PID52000/start **2026-09-29 21:49:32**, `.venv/Scripts/sora.exe`, rechecked unchanged during this pass. No owner environment sync, data/settings migration, restart/reload, provider/paid model/device/avatar operation or denied native retry. Verification uses the separate environment and temporary profiles. Source edits do not load this worker into the already-running older Core.

Migration12, AppSettings v9, UI preferences v1 and default Desktop remain unchanged. Existing clock/spec/storage schemas and historical records are preserved except the declared API availability-enum extension. No manual Run now endpoint, shared Automations panel, live-provider/native/physical/ordinary-release acceptance or whole-stage completion is claimed. The full GUI goal remains active.
