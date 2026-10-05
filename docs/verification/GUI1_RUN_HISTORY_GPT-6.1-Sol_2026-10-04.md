# GUI-1c task attempts, registered artifacts and public activity — verification

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-04 02:47:15 +01:00**, Europe/London. Status: **implemented slice / GUI-1c in progress**. No full-stage completion timestamp or ordinary default switch.

## Implementation

Added two owner-local GET routes over canonical tasks/agent_runs/normalized_results: `/api/v1/tasks/{task_id}/runs` and `/api/v1/tasks/{task_id}/runs/{run_id}`. No database migration/history engine. Page limits1–100 (default50), latest-first task-bound cursors and fixed admission ceiling keep retries admitted later outside an existing traversal. Existing attempt status remains live at each read; Refresh establishes a new ceiling. Owner/task/run/payload identity checks reject wrong targets. Remote scopes receive403; other owners/missing task-runs404. Schema exports include task-run-page/task-run-evidence.

Exact attempt evidence projects outcome, summary/conclusion, selected public report lists, failure and reported changelog metadata with a32768-character shared report-text budget, at most64 items per list, separate4096-character error limit, omission counts and truncation flag. Private patches/internal facts/capture reasoning/trace/session usage details are not rendered. A missing normalized result stays missing; latest task result is never substituted. Historic exact model/effort are not fabricated from current TaskRecord values. This is complete recorded-attempt pagination, not unbounded/raw provider-log access or independent filesystem verification.

Artifact rows derive from projected exact files_changed/changelog paths, up to65 reported paths and64 registered matches total. Matching references come from Core's existing owner/device/project-scoped content resolver and exact path match. Unregistered/relative/unprojected paths are inert. Open uses a fixed typed navigation request through the shared session, with fresh registration/epoch/serialized mutation/ACK validation. No arbitrary path/executable/URL launch or new grant flow.

Activity integrates All attempts/files with explicit Refresh/Previous/Next/Inspect/Open, separate from latest task evidence and Cancel/Steer. Exact-ID inspection pins at most one record outside the latest100 list. Async read/selection/epoch guards reject stale replies; disconnect requires explicit reinspection before Open becomes available. Native accessible controls/read-only inert text are source implementation, not screen-reader/physical layout acceptance.

WidgetSync's existing event pagination retains at most64 allowlisted public task/run metadata records, deduplicated by event ID and cleared on resync/Core epoch. No event payload is copied. Shared-host Chat renders up to8 compact horizontally scrolling evidence buttons with bounded ellipsis/tooltips; unchanged metadata does not rebuild the row. Buttons open the exact task via the host. Actual source/event/sequence/task/run/correlation/time are retained. No invented association to Chat nonce, worker completion proof or UI-presentation acknowledgement. No extra panel timer/connection/state database/model call.

## Fresh verification

| Check | Result |
|---|---|
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **210 passed**, zero failed/skipped; final source exit0 |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **706 Python passed /25 opt-in skipped in85.84s**, **8 PWA passed**, mypy266/lint/schema/compile passed; exec15234 final exit0 |
| Shell/Desktop/Widget `dotnet build ... --verbosity quiet` | all final source zero warnings/errors |
| `./scripts/verify-shell-launchers.ps1` | existing real-launcher AST/default/explicit/retained-panel/unsupported-effort checks pass; effect-free receiver only |
| Preservation read-back | all9 supplied reference/draft/overview file sizes and SHA-256 hashes match prior baseline; original GUI-0a/0c/0d completion entries remain19:24:55 |
| `git diff --check` | exit0, existing LF→CRLF warnings only; explicit read-back/tests cover untracked source |

**18 new C# cases (192→210)** cover allowlisted/private-free public metadata, malformed identifiers/source/correlation/time, bounded replay deduplication/resync/epoch reset, failed projection atomicity, model-down read-only exact-task history outside current task list, old-Core async reply rejection, cross-task page/duplicate run rejection, host block/no request, path/cursor injection rejection and inert exact-run/provider coverage formatting.

**Two new Python tests** include many deterministic/in-process and actual isolated HTTP assertions: planned empty history, first failed attempt then successful retry and later failure, exact previous result vs current, fixed pagination ceiling/new Refresh/no duplicates, invalid cursor/limits, other-owner/unknown-run404 and remote403; bounded report omissions/private field filtering, exact registered path vs unregistered relative/changelog paths, actual content registration plus HTTP device isolation, valid oversized report clipping and pending retry without result. Test-only validated report fixture updates use the isolated temporary database, not owner data. No real agent/model/file-opening probe.

The first broader verification attempt found two test variable typing errors, corrected before a successful full run; a later source lint error was corrected before the final run. An invalid oversized test report was replaced with schema-valid bounded fields. These intermediate failures are not described as passing. Python/API/schema source was unchanged after the successful full run; subsequent C#-only exact-ID/ellipsis refinements were followed by final210 tests and all three builds.

**Final-source confirmation at2026-10-04 02:53:20 +01:00:** exact-ID lookup clears the previous selection while resolving, so the previous task is not displayed as the requested target. Final210 C# checks and all three zero-warning/error builds pass after this source refinement. All99 local links in the four updated/new documents resolve; the roadmap still has exactly3 completion checkboxes and the original3 completion timestamps. Owner PID52000/start remains unchanged. These are source/component/preservation checks, not native input proof.

## Evidence boundary and remaining acceptance

No new native window capture/input, successful GUI attachment/history/page/chip/file-open action, paid provider probe, model load or microphone/voice session occurred. The preceding Board/Content fixture setup policy rejection was not retried through another execution path. Component/HTTP tests do not satisfy the native GUI gate. No fixture listener/worker was left running by the new tests; servers/runtimes close in finally blocks.

Owner Core **PID52000**, start **2026-09-29 21:49:32** local, remains `.venv\Scripts\sora.exe`; no owner restart, settings/data write or environment replacement. Dedicated UV verification environment remains separate. Canonical AppSettingsv9 and UI preferencev1 are unchanged. No reset, commit, force kill or compatibility removal.

Native tasks outside the latest list; unknown task clearing; page/selection/hide/reopen/racing reads; actual registered handler failure/open; chip overflow/keyboard/tooltips; mixed-DPI/high contrast/screen reader and model-down/offline recovery remain required. Prior host/Chat/Agents/Paths/Board/Content/configured-provider acceptance gaps remain open. Next implementation: shared GUI-1d voice, then GUI-2 categorized full Settings; GUI-3–GUI-6 still required.

[Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress changelog](../../changelog/2026-10-04T024715+0100_GUI1c-RUN-HISTORY-PROGRESS_GPT-6.1-Sol.md).
