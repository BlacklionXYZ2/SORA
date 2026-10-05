# GUI-4a Automation storage verification

Model name: **GPT-6.1 Sol**. Source checkpoint **2026-10-04 12:48:42 +01:00**, Europe/London. Status: **implemented source/component slice; GUI-4a in progress**. [Contract](../gui/GUI4_AUTOMATION_STORAGE_CONTRACT_GPT-6.1-Sol_2026-10-04.md).

## Fresh checks

- **44 focused Python passed in7.62s**:22 new Automation cases, existing database and20 Memory-mutation cases. Actual authenticated temporary HTTP/SQLite, no owner data/provider calls. Remote-scope refusal is a direct route fixture, not a newly paired live device. Reservations are direct internal calls with injected clocks, not a scheduler timer.
- **369 C# component passed**, zero failed/skipped; all three Windows client builds zero warnings/errors and effect-free launcher forwarding passed at **2026-10-04 12:48:42 +01:00**. No new C# source/test; this is regression, not Automations GUI acceptance.
- Full isolated `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1`, live exec51187: lint/mypy283 passed,887 tests collected. Final terminal result is appended only after the same process completes; progress is not a passing result.

Automation coverage: actual create/edit/resume/pause/delete/detail/history/receipt behavior with explicit worker-unavailable status; identical concurrent requests/changed-key conflicts/stale epoch/version/state; literal Unicode-capable name filtering, summary privacy, owner/global/foreign-project/foreign-owner isolation; signed filter/limit/epoch-bound paging, later-admission exclusion,256-record scan continuation; malformed/authority fields/method/remote fences; event/outbox failure rolls back definition/revision/receipt, corrupt stored values are redacted; actual11→12 migration preserves task/run/message/revision and new-store reopening preserves the original receipt with committed/current epoch distinction; future/no-effect and unique concurrent reservation, behavior snapshot, restart dedup, overlap skip, unchanged-trigger edit preserves next slot, stale reservation version rejected; history paging has no duplicate/fake task evidence; missed recovery advances without a backlog burst. A second SQLite connection writes during page decoding and the returned page/revision still prove one read snapshot.

Initial failures were draft SQL formatting/type annotations and test use of `SoraRepository.list_tasks` instead of the actual runtime repository. These were corrected and rerun; no failed result is reported as passing. Existing migration tests now expect schema12 while retaining their preservation assertions, not rewriting earlier11 checkpoints.

## Environment and limits

Owner Core PID52000/start **2026-09-29 21:49:32**, `.venv/Scripts/sora.exe`, rechecked unchanged at **2026-10-04 12:48:42 +01:00**. No owner migration/settings/data/environment change, restart/reload, device/avatar/provider/model operation or denied native retry. Isolated tests use temporary DBs and the separate environment. A running older Core does not load these routes or migrate data merely because source was edited.

Source migration now12; AppSettingsv9/UIpreferencesv1/default Desktop unchanged. API always reports scheduler unavailable; no agent task was created by saves/reservations. No worker lifecycle, actual task admission/recovery/manual Run now, native Automations GUI or scheduled-run acceptance yet. Earlier Memory/native/live/physical/release gaps and full goal remain open.

## Final regression

**2026-10-04 12:51:26 +01:00:** Same exec51187 returned terminal exit0. Final-source `./scripts/verify.ps1`: **862 Python passed /25 opt-in skipped in102.09s; 8 PWA; mypy283/lint/exported-schema check/compile passed**. No source/test/schema change afterward; later documentation only. This is storage/component regression, not a worker/admission/native/live/release completion claim.
