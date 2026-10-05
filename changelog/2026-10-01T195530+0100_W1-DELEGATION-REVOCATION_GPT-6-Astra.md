# W1 delegation revocation — GPT-6 Astra

Slice completed and verified: **2026-10-01 19:55:30 +01:00 (Europe/London)**.
Workstream status: **W1 in progress**. Overall frontend goal remains active.

## Implemented

- Persisted an internal delegation_epoch in unified settings and optional local_delegation_epoch in agent run records. These are provenance/version metadata, not permissions to request or GUI-editable preferences. Existing run payloads remain readable. Exported both affected schemas.
- GUI saves increment the epoch when delegation changes. Explicit disk refresh normalizes hand-edited settings without allowing the running controller's epoch to move backwards. Unrelated preferences do not revoke delegation.
- Local submit, start-from-board, retry and fan-out preserve the admitted epoch. Remote/legacy runs are not relabelled owner-local based on device text or the presence of a settings file.
- Added execution-time guards shared by initial launch, resume, fallback and fan-out. Queued local work from before OFF→ON is cancelled instead of launched, including after restart. A new explicit request can run under the new epoch.
- Disabling delegation schedules cancellation of old pending runs independently of worker availability. Active local runs are tracked with the actual bound/fallback provider instance. Cancellation RPCs have a five-second bound and audit request-sent versus unknown/failure; a successful RPC is not claimed as proof of process exit. Normal provider results still establish reported outcomes.
- Recheck after a launch acknowledgement handles revocation while launch itself was in flight. Cancellation-requested state is preserved when a late launch acknowledgement arrives.
- Made pending-run cancellation atomic with worker lease admission, and repeated cancellation idempotent. Fixed fan-out cancellation trying to repeat a transition and getting stuck before its terminal cancelled state.
- Runtime shutdown waits for pending policy-cancellation work. No owner runtime restart, paid model invocation, agent project mutation or computer input was performed in this pass.

## Verification

Final scripts/verify.ps1 after the final source changes: **494 passed, 13 opt-in skipped, 77.79 seconds**; Ruff, mypy (**217 files**), generated schema freshness, compileall and **7 PWA tests** passed. C# tests: **36 passed**. Scoped git diff whitespace check passed (normal LF/CRLF notices).

Eight new deterministic regression cases in tests/runtime/test_delegation_policy.py cover active/queued OFF→ON behaviour, persisted policy across restart, remote/legacy separation, the common resume/fallback launch guard, monotonic disk refresh, fan-out cancellation and both orderings of worker-admission/cancellation. Earlier intermediate runs caught a fan-out state transition bug and an overly broad UUID substring in the test's branch selector; both were corrected before the final gate.

Changed implementation files: src/sora/contracts/models.py; src/sora/runtime/app_settings.py, repository.py and service.py; contracts/schema/v1/agent-run-record.schema.json and app-settings.schema.json. Tests: new test_delegation_policy.py and updated test_app_settings.py metadata expectations.

## Remaining acceptance

This verifies Core scheduling and deterministic adapters, not actual Codex/Hermes/Antigravity process-stop acknowledgement or a held real-project write-root lease. Cancellation cannot undo effects already performed; provider cancellation failure is logged as unknown. Real-provider cancellation/lease ownership remains part of W2 acceptance.

W1 still needs the remaining internal/legacy caller audit, extension/integration effect registration, full voice/pre-effect audit, recovery fault-order tests, startup consolidation and GUI/native/renderer/restart acceptance. GUI access-switch clicking remains outside Computer Use's permitted actions; isolated API tests exercise those settings. No new GUI visual pass was claimed here. Native perception, the tool/model catalogue, action orchestration, passive vision, voice and final frontend acceptance remain in the [full tracker](../docs/verification/FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md).
