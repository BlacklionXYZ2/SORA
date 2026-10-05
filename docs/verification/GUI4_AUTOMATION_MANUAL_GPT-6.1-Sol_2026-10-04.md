# GUI-4 manual Run now verification

Model name: **GPT-6.1 Sol**. Source checkpoint **2026-10-04 13:44:05 +01:00**, Europe/London. Status: **implemented source/component slice; GUI-4a/c in progress**. [Contract](../gui/GUI4_AUTOMATION_MANUAL_CONTRACT_GPT-6.1-Sol_2026-10-04.md).

## Fresh checks

- **81 focused Python passed in14.87 seconds**, process77299 terminal exit0 observed13:42:53: 11 new manual HTTP cases, 31 worker cases including three new manual recovery/rollback cases, 22 storage and 17 lifecycle cases. Subsequent import-order cleanup changes no test logic; final full verification below includes it.
- **369 C# component passed**, no failed/skipped; three Windows clients built with zero warnings/errors; effect-free forwarding passed at13:44:05. No C# source/test changes; this does not certify an Automations GUI.
- Final isolated `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` process45515: lint/mypy287 passed, 929 tests collected. Final terminal result is appended only after observing that same process complete, not inferred from progress.

Coverage: authenticated actual active/paused manual task execution using saved behavior; no scheduled-slot/version/definition drift; historical receipt distinct from later completed occurrence; concurrent identical requests yield one reservation/task; changed-body and mutation-key conflicts; manual overlap/Unknown non-bypass; worker-unavailable blocked attempt never launches on later worker start; fresh static-policy failure recorded without private error text; epoch/version/scoped hidden-project/remote/closed-body/query/method fences; injected event failure atomically rolls back revision/occurrence/receipt; historical replay after soft delete does not resurrect or run; actual temporary Core reopen admits the already-accepted request once within expiry and blocks it after expiry; cross-epoch receipt reconciliation retains original occurrence/committed epoch; manual clock rollback waits and definition changes retire pending admission. All effects occur in temporary fixture databases through the deterministic provider, not paid/live agents or owner data.

Initial draft failures were test HTTP constructor shape, long SQL literal, test type narrowing and import ordering. They were corrected/rerun; no failed check is reported as passing. Existing worker/mutation/schema evidence is preserved rather than replacing old results with new totals.

## Final full regression

**2026-10-04 13:47:07 +01:00:** Same isolated process45515 returned terminal exit0. Final-source `./scripts/verify.ps1`: **904 Python passed /25 opt-in skipped in110.52 seconds; 8 PWA; mypy287/lint/exported-schema/compilation passed**. Source/tests/schemas unchanged after the run began; later documentation only. This is backend/component regression, not native/live/release acceptance.

## Environment and limits

Owner Core PID52000/start **2026-09-29 21:49:32**, `.venv/Scripts/sora.exe`, rechecked unchanged at13:44:05. No owner environment sync, settings/data migration, restart/reload, provider/model/device/avatar action or denied native retry. Source migration12, AppSettings v9, UI preferences v1 and default Desktop unchanged. The separate verification environment and temporary Core reopen are not an owner restart.

The original Automations reference was inspected without editing. No native shared Automations window/New/Edit/control input, live-provider/real wall-time/full persisted DST/interval/physical/ordinary-release acceptance is claimed. GUI-4a/c, GUI-4b and all inherited full-GUI gates remain open; next shared window/editor and task/evidence/semantic controls.
