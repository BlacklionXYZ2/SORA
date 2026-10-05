# P15.8 canonical Kanban desktop object — GPT-6

Status: **completed 2026-09-23 13:19:26 +01:00 (Europe/London)**.
This closes P15.8 only. P15.2 and P15.7 retain their separate in-review gates.

## Implemented

- Added `planned` to the canonical task lifecycle. A board plan persists one
  `TaskRecord`, an owner-visible deterministic acknowledgement and an
  idempotency record, but **no** `AgentRunRecord`, lease, provider selection or
  queue entry. Schema migration 8 adds only the plan-idempotency table.
- Explicit start attaches the first pending run atomically to the same task ID.
  Duplicate starts conflict, an unregistered requested Codex provider fails
  without fallback, and planning does not consume runtime run capacity. Retry
  adds a new numbered run while preserving earlier run evidence.
- Replaced the placeholder Kanban SQL with one scoped projection of canonical
  task records and creator messages. TODO means `planned`; DOING means queued,
  routing, reasoning, working, waiting, cancel-requested or interrupted; DONE
  means completed, failed or cancelled. The exact status, specialist, attention
  flag, run count, referent and result IDs remain available on the card. No
  board-owned duplicate task state or Hermes sync was added.
- Planned tasks are excluded from the companion's active-background-worker
  count; a regression assertion prevents a saved TODO from falsely making
  SORA appear busy.
- Added a separate Windows Kanban window from the full app's Activity view.
  Focused mode has three lanes and explicit plan/start-Codex/start-auto/retry
  controls; compact mode displays readable counts and card summaries. Chat's
  explicit “Fix this later (TODO)” button creates the same canonical plan,
  with no automatic delegation. PWA task presentation labels plans as unstarted
  and suppresses steer/cancel controls until a run exists.

## Verification

| Check | Result |
|---|---|
| `uv run --locked pytest -q tests/api/test_kanban_board.py tests/attention/test_attention_objects.py tests/persistence/test_database.py` | 10 passed. Plan idempotency, no-run invariant, explicit provider failure, same task ID on start, one-run duplicate suppression, mapping and retry history passed. |
| Final `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1` | 348 Python passed; 10 explicit opt-in skips. Ruff, strict mypy across 187 sources, schemas, compileall and browser 7/7 passed. |
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | 30/30 passed, including exact board-path validation and shared widget/full-app projection convergence. |
| `dotnet build clients/desktop_app/desktop_app.csproj --verbosity quiet` | Zero warnings/errors after final UI changes. |
| Native Windows UI against isolated deterministic Core | Created “Review the QA fixture report later” in TODO with no run; selected it, saw an explicit start confirmation, then observed it in DONE after the same task completed. Activity showed the same description/status. Final focused view showed all controls and status; final compact view showed readable per-column counts and the completed card. This is a deterministic fixture, not a live Cody/Hermes run. |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1 -ReleaseId sora-p15.8-acceptance-20260923-r2 -ReuseVerifiedUnityBuild` | Built the final self-contained Core/widget/full-app bundle after the active-worker correction, reusing the previously verified Unity player rather than claiming a fresh Unity test. |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-release.ps1 -Bundle .local/releases/sora-p15.8-acceptance-20260923-r2 -RequireWidget -RequireDesktop` | Passed clean install, schema-8 update, rollback, data-retaining uninstall and reinstall; widget/full-app preferences survived. Record: `.local/p15.3-release-acceptance-3daef757-5ccf-4902-9bdd-2a465db882fe/acceptance.json`. |

Final archive: `.local/releases/sora-p15.8-acceptance-20260923-r2.zip`,
421,175,301 bytes, SHA-256
`92c1c7f23241b222c5df35d8948ebebc1410f89ab68b01a6939dea6d09b451dc`.
No commit, tag or staging operation was performed.

## Limits and owner checks

- The board is an owner-local desktop client of canonical Core state, not a
  separate server, public extension manager or autonomous scheduler. The
  remote route allowlist still excludes board mutation and the objects
  projection. “Get Cody to do it” requires an actually registered/configured
  Codex provider and the existing P05 coding-workspace boundary.
- Animations and Hermes board sync are optional and absent. A later Blender
  clip can improve presentation without changing task/run authority.
- The [owner manual-verification checklist](OWNER_MANUAL_ACCEPTANCE_CHECKLIST_2026-09-23.md)
  records prior physical-device and subjective checks. P15.2's real phone and
  P15.7's broader settings/four-surface parity remain open; P15.8 does not
  silently certify either.
