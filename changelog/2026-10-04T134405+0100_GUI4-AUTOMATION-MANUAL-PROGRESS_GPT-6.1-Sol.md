# GUI-4 durable manual Run now progress

Model name: **GPT-6.1 Sol**. Source checkpoint **2026-10-04 13:44:05 +01:00**, Europe/London. Status: **implemented source/component slice; GUI-4a/c in progress**, not stage completion.

## Changes implemented

- Added closed/exported `AutomationRunNow` and owner-local POST `/api/v1/automations/{id}/run-now`; exact Core/version/scope/body guards and stable receipt keys. New attempts return202, identical replay200; neither claims task completion.
- Added atomic manual occurrence/snapshot/submission key, revision/content-free event/outbox and historical receipt using existing migration12 storage. Active/paused definitions supported; saved state/version/next slot untouched. Overlap skips, unavailable workers block, and no unsupported tool/authority/model override is accepted.
- Extended AutomationAck with manual action/optional occurrence and exact historical invariant validation; old mutation receipts remain compatible. Replay survives delete/new Core without overwriting original outcome or creating work; changed or reused mutation keys conflict.
- Integrated manual admission/recovery through the existing worker/transaction/queue. Added 300-second unadmitted request expiry checked during recovery and SQL admission; clock rollback waits, version changes retire pending requests, Unknown work blocks overlap and exact submissions are never scheduler-replayed.
- Added 11 temporary HTTP manual cases and three worker recovery/rollback cases; exported the new schema and updated acknowledgement schema. Inspected original Automations image; wrote contract/report and reconciled current roadmap/runbook without claiming a GUI control exists.

## Verification and next scope

[Verification](../docs/verification/GUI4_AUTOMATION_MANUAL_GPT-6.1-Sol_2026-10-04.md): 81 focused Python passes, 369 C# regression passes, three zero-warning/error Windows builds and effect-free forwarding. Final full isolated process45515 result is recorded after observed completion, not guessed from progress.

Owner runtime/settings/data/environment and reference/contributor originals preserved. No native/live-provider/physical/release acceptance or stage checkbox/completion time added. Full GUI goal stays active. Next shared reference-based Automations window, retained full editor, exact task/evidence/receipt controls and semantic presentation; keep all earlier connected gates and real graph/design/release scope.

Final full isolated regression observed **2026-10-04 13:47:07 +01:00**, same process45515 terminal exit0: **904 Python passed /25 opt-in skipped in110.52 seconds; 8 PWA; mypy287/lint/exported-schema/compilation passed**. Later edits are documentation only. Roadmap nowv1.32; no whole-stage completion time.
